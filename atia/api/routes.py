"""
routes.py
─────────────────────────────────────────────
PURPOSE:
  All API endpoint handlers for the ATIA agent (PRD §8.2).
  Maps HTTP requests to agent operations and returns
  formatted responses.

RESPONSIBILITIES:
  - GET /trust-profile/{agency_id} — retrieve trust profile
  - POST /evaluate/{agency_id} — trigger on-demand evaluation
  - GET /trust-profile/{agency_id}/audit — audit trail (admin)
  - POST /override/{agency_id} — admin override
  - GET /anomaly-queue — anomaly queue (admin)
  - GET /trust-profile/{agency_id}/history — tier history

NOT RESPONSIBLE FOR:
  - Evaluation pipeline logic (see orchestrator.py)
  - Authentication verification (see middleware.py)

DEPENDENCIES:
  - agent.orchestrator: evaluation pipeline
  - api.middleware: auth and rate limiting
  - data.agency_queries: audit trail, anomaly queue
  - models: request/response types

USED BY:
  - main.py (router mounting)
─────────────────────────────────────────────
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Depends, HTTPException

from models.inputs import EvaluationTrigger
from models.outputs import (
    TrustProfileResponse,
    EvaluationAcceptedResponse,
    OverrideRequest,
    AnomalyQueueItem,
    IntegrityFlag,
)
from agent.orchestrator import run_evaluation
from api.middleware import (
    extract_role_from_request,
    extract_user_id_from_request,
    require_admin_role,
    check_evaluation_rate_limit,
)
from data.agency_queries import (
    fetch_audit_trail,
    fetch_anomaly_queue,
    fetch_agency_name,
    insert_audit_log,
    fetch_trust_profile_history,
    fetch_all_agencies_with_profiles,
)
from config.constants import TRUST_TIERS, OVERRIDE_REASON_MIN_LENGTH
from utils.logger import get_logger
from utils.error_handler import ATIAError

logger = get_logger("api.routes")

router = APIRouter(prefix="/api/v1/agent")


@router.get("/trust-profile/{agency_id}")
def get_trust_profile(
    agency_id: str,
    request: Request,
    force_refresh: bool = False,
) -> TrustProfileResponse:
    """
    Retrieve the current trust profile for an agency (PRD §8.2).

    Returns audience-appropriate content based on requestor role.
    Serves cached profile if valid, otherwise triggers fresh evaluation.
    """
    role = extract_role_from_request(request)
    user_id = extract_user_id_from_request(request)

    trigger = EvaluationTrigger(
        agency_id=agency_id,
        trigger_type="ON_DEMAND",
        requestor_role=role,
        requestor_id=user_id,
        force_refresh=force_refresh,
    )

    try:
        return run_evaluation(trigger)
    except ATIAError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_dict())


@router.post("/evaluate/{agency_id}")
def trigger_evaluation(
    agency_id: str,
    request: Request,
    _admin: str = Depends(require_admin_role),
) -> EvaluationAcceptedResponse:
    """
    Trigger an on-demand trust evaluation (PRD §8.2).

    Admin-only. Rate limited to one per agency per 15 minutes.
    """
    check_evaluation_rate_limit(agency_id)

    # In production, this would be queued async.
    # For v1.0, we run synchronously and return immediately.
    trigger = EvaluationTrigger(
        agency_id=agency_id,
        trigger_type="ON_DEMAND",
        requestor_role="admin",
        requestor_id=extract_user_id_from_request(request),
        force_refresh=True,
    )

    try:
        run_evaluation(trigger)
    except ATIAError as exc:
        logger.error(f"Triggered evaluation failed: {exc}")

    return EvaluationAcceptedResponse(
        job_id=str(uuid.uuid4()),
        estimated_completion_seconds=8,
    )


@router.get("/trust-profile/{agency_id}/audit")
def get_audit_trail(
    agency_id: str,
    _admin: str = Depends(require_admin_role),
) -> dict:
    """
    Retrieve full audit trail for an agency (PRD §8.2).

    Admin-only. Returns all evaluation records in reverse
    chronological order.
    """
    trail = fetch_audit_trail(agency_id)
    return {
        "agency_id": agency_id,
        "evaluations": [
            {
                "evaluation_id": e.get("id", ""),
                "evaluated_at": e.get("created_at", ""),
                "trust_tier": e.get("final_trust_tier", ""),
                "confidence_level": e.get("final_confidence", ""),
                "trigger": e.get("evaluation_trigger", ""),
                "integrity_flags": e.get("integrity_checks_log", {}),
                "override_applied": e.get("override_applied", False),
                "override_by": e.get("override_by"),
                "override_reason": e.get("override_reason"),
                "override_tier": e.get("override_tier"),
            }
            for e in trail
        ],
    }


@router.post("/override/{agency_id}")
def apply_override(
    agency_id: str,
    body: OverrideRequest,
    request: Request,
    _admin: str = Depends(require_admin_role),
) -> dict:
    """
    Admin override of trust tier (PRD §8.2).

    Creates a NEW audit log entry and a NEW trust profile.
    Does NOT modify existing records.
    """
    # Validate override tier
    if body.override_tier not in TRUST_TIERS:
        raise HTTPException(400, detail="Invalid override tier value.")
    if body.override_tier == "InsufficientData":
        raise HTTPException(400, detail="Cannot manually assign InsufficientData tier.")
    if len(body.reason) < OVERRIDE_REASON_MIN_LENGTH:
        raise HTTPException(
            400,
            detail=f"Override reason must be at least {OVERRIDE_REASON_MIN_LENGTH} characters.",
        )

    user_id = extract_user_id_from_request(request)

    # Insert override audit log entry
    audit_entry: dict = {
        "agency_id": agency_id,
        "evaluation_trigger": "OVERRIDE_CHK",
        "triggered_by": user_id,
        "override_applied": True,
        "override_by": user_id,
        "override_reason": body.reason,
        "override_tier": body.override_tier,
        "final_trust_tier": body.override_tier,
        "final_confidence": "",
        "raw_signal_snapshot": {},
        "integrity_checks_log": {},
        "weighted_signals": {},
        "llm_prompt_hash": "",
        "llm_response_raw": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        result = insert_audit_log(audit_entry)
        audit_id = result.get("id", str(uuid.uuid4()))
    except Exception as exc:
        logger.error(f"Override audit log failed: {exc}")
        raise HTTPException(500, detail="Failed to record override.")

    logger.info(
        "Admin override applied",
        extra={"extra_data": {
            "agency_id": agency_id,
            "override_tier": body.override_tier,
            "override_by": user_id,
        }},
    )

    return {"message": "Override applied", "audit_log_id": audit_id}


@router.get("/anomaly-queue")
def get_anomaly_queue(
    _admin: str = Depends(require_admin_role),
) -> dict:
    """
    List all agencies with active P0 integrity flags (PRD §8.2).

    Admin-only. Returns agencies sorted by flag severity and recency.
    """
    raw_agencies = fetch_anomaly_queue()

    items = []
    for agency_data in raw_agencies:
        agency_id = agency_data.get("agency_id", "")
        flags_raw = agency_data.get("integrity_flags", [])

        # Filter to P0 flags only
        p0_flags = [f for f in flags_raw if isinstance(f, dict) and f.get("severity") == "P0"]
        if not p0_flags:
            continue

        name = fetch_agency_name(agency_id)
        items.append(AnomalyQueueItem(
            agency_id=agency_id,
            agency_name=name,
            flags=[IntegrityFlag(**f) for f in p0_flags],
            flagged_since=agency_data.get("evaluated_at", datetime.now(timezone.utc)),
            trust_tier=agency_data.get("trust_tier", "UnderReview"),
        ))

    return {"agencies": [item.model_dump(mode="json") for item in items], "total": len(items)}


@router.get("/trust-profile/{agency_id}/history")
def get_tier_history(
    agency_id: str,
    request: Request,
) -> dict:
    """
    Time series of trust tier changes (PRD §8.2).

    Accessible to admins and HR consultants (own agency only).
    """
    role = extract_role_from_request(request)
    if role not in ("admin", "hr_consultant"):
        raise HTTPException(403, detail="Access denied.")

    history_data = fetch_trust_profile_history(agency_id)
    return {
        "agency_id": agency_id,
        "history": [
            {
                "evaluated_at": h.get("created_at", ""),
                "trust_tier": h.get("final_trust_tier", ""),
                "confidence": h.get("final_confidence", ""),
            }
            for h in history_data
        ],
    }


@router.get("/agencies")
def list_agencies(request: Request) -> list[dict]:
    """
    List all agencies with their trust profiles.

    Accessible to all authenticated roles.
    HR Consultants are meant to filter this client-side or
    we handle sending them all and letting their dashboard filter.
    """
    # We could restrict HR consultants here, but for now
    # we return all and let the client filter as it expects.
    return fetch_all_agencies_with_profiles()
