"""
orchestrator.py
─────────────────────────────────────────────
PURPOSE:
  Controls the ATIA evaluation pipeline from trigger to response.
  Implements Steps 1-8 of PRD §6.2 in sequence.
  Delegates ALL actual work to specialized modules.

RESPONSIBILITIES:
  - Step 1: Trigger classification + cache check
  - Step 2: Data retrieval (delegates to agency_queries)
  - Step 3: Data sufficiency check
  - Step 4: Integrity assessment (delegates to signal_auditor)
  - Step 5: Signal weighting (delegates to weighting_engine)
  - Step 6: Trust synthesis (delegates to trust_reasoner)
  - Step 7: Validation + storage
  - Step 8: Audience-aware response delivery

NOT RESPONSIBLE FOR:
  - Individual check logic (signal_auditor.py)
  - Weight calculations (weighting_engine.py)
  - LLM communication (trust_reasoner.py, llm/client.py)
  - HTTP handling (api/routes.py)

DEPENDENCIES:
  - All agent modules, data, memory, models, utils, llm

USED BY:
  - api/routes.py (on-demand evaluations)
  - api/event_listener.py (event-triggered re-evaluations)
─────────────────────────────────────────────
"""

import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from config.constants import (
    MIN_REVIEWS_FOR_EVALUATION, MIN_PLACEMENTS_FOR_EVALUATION,
    CONFIDENCE_HIGH_MIN_REVIEWS, CONFIDENCE_MEDIUM_MIN_REVIEWS,
    SEVERITY_P0,
)
from config.settings import get_settings
from models.inputs import EvaluationTrigger, RawDataPackage
from models.outputs import (
    TrustProfile, AuditLogEntry, SignalSummary,
    AudienceSummaries, TrustProfileResponse,
)
from models.internal import SufficiencyResult, IntegrityResult, EvaluationLog
from agent.signal_auditor import run_all_integrity_checks
from agent.weighting_engine import compute_weighted_signals
from agent.trust_reasoner import synthesize_trust_profile
from agent.responder import format_response_for_role
from data.agency_queries import (
    fetch_raw_data_package, upsert_trust_profile, insert_audit_log,
)
from memory.cache_manager import (
    get_cached_profile, is_cache_valid, get_stale_cache_if_available,
)
from utils.validators import validate_and_correct_profile
from utils.logger import get_logger
from utils.error_handler import LLMError, LLMParseError, DataRetrievalError

logger = get_logger("agent.orchestrator")


def run_evaluation(trigger: EvaluationTrigger) -> TrustProfileResponse:
    """
    Execute the complete ATIA evaluation pipeline (Steps 1-8).

    This is the single entry point for ALL evaluations — on-demand,
    event-triggered, cron, and override verification.

    Args:
        trigger: The evaluation trigger with agency_id and context.

    Returns:
        TrustProfileResponse formatted for the requestor's role.
    """
    start_time = time.time()
    eval_log = EvaluationLog(
        agency_id=trigger.agency_id,
        evaluation_id=str(uuid.uuid4()),
        trigger_type=trigger.trigger_type,
    )

    try:
        # ── Step 1: Trigger Classification + Cache Check ────
        cached = _step1_cache_check(trigger)
        if cached:
            eval_log.cache_hit = True
            eval_log.duration_ms = _elapsed_ms(start_time)
            _log_evaluation(eval_log)
            return cached

        # ── Step 2: Data Retrieval ──────────────────────────
        data = _step2_retrieve_data(trigger.agency_id)

        # ── Step 3: Data Sufficiency Check ──────────────────
        sufficiency = _step3_check_sufficiency(data)
        eval_log.data_sufficiency_result = sufficiency.model_dump()

        if not sufficiency.is_sufficient:
            return _handle_insufficient_data(
                trigger, data, sufficiency, eval_log, start_time,
            )

        # ── Step 4: Signal Integrity Assessment ─────────────
        integrity = _step4_integrity_checks(data)
        eval_log.integrity_checks = {
            c.check_id: c.model_dump() for c in integrity.checks
        }
        eval_log.flags_triggered = [f.flag_id for f in integrity.flags]
        eval_log.llm_call_count += (1 if any(
            c.check_id == "CHECK-E" for c in integrity.checks if c.triggered
        ) else 0)

        # ── Step 5: Signal Weighting ────────────────────────
        weighted = compute_weighted_signals(data, integrity)

        # ── Step 6: Trust Profile Synthesis (LLM) ───────────
        draft, llm_response = synthesize_trust_profile(
            agency_id=trigger.agency_id,
            weighted_signals=weighted,
            integrity=integrity,
            sufficiency=sufficiency,
            previous_profile=data.previous_profile,
        )
        eval_log.llm_call_count += 1
        eval_log.llm_total_tokens_used += (
            llm_response.input_tokens + llm_response.output_tokens
        )

        # ── Step 7: Validation + Storage ────────────────────
        corrected = validate_and_correct_profile(draft, sufficiency, integrity)
        profile = _step7_store_profile(
            trigger, data, corrected, integrity, weighted,
            llm_response, eval_log,
        )

        eval_log.final_tier = profile.trust_tier
        eval_log.confidence_level = profile.confidence_level

        # ── Step 8: Audience-Aware Response ──────────────────
        eval_log.duration_ms = _elapsed_ms(start_time)
        _log_evaluation(eval_log)

        return format_response_for_role(profile, trigger.requestor_role)

    except (LLMError, LLMParseError) as exc:
        logger.error(f"LLM failure during evaluation: {exc}")
        return _fallback_to_cache(trigger, eval_log, start_time, str(exc))

    except DataRetrievalError as exc:
        logger.error(f"Data retrieval failure: {exc}")
        return _fallback_to_cache(trigger, eval_log, start_time, str(exc))

    except Exception as exc:
        logger.error(f"Unexpected evaluation error: {exc}", exc_info=True)
        return _fallback_to_cache(trigger, eval_log, start_time, str(exc))


# ─── Pipeline Steps ────────────────────────────────────────

def _step1_cache_check(
    trigger: EvaluationTrigger,
) -> Optional[TrustProfileResponse]:
    """Step 1: Check cache. Return profile if valid, None otherwise."""
    if trigger.force_refresh:
        return None
    if trigger.trigger_type != "ON_DEMAND":
        return None

    cached = get_cached_profile(trigger.agency_id)
    if cached and is_cache_valid(cached, trigger.agency_id):
        logger.info("Serving cached profile", extra={"extra_data": {
            "agency_id": trigger.agency_id,
        }})
        profile = _dict_to_trust_profile(cached)
        return format_response_for_role(profile, trigger.requestor_role)

    return None


def _step2_retrieve_data(agency_id: str) -> RawDataPackage:
    """Step 2: Retrieve all agency data from Supabase."""
    logger.info("Retrieving agency data", extra={"extra_data": {
        "agency_id": agency_id,
    }})
    return fetch_raw_data_package(agency_id)


def _step3_check_sufficiency(data: RawDataPackage) -> SufficiencyResult:
    """Step 3: Check if enough data exists for a meaningful evaluation."""
    review_count = len(data.reviews)
    placement_count = len(data.placements)
    is_sufficient = (
        review_count >= MIN_REVIEWS_FOR_EVALUATION
        or placement_count >= MIN_PLACEMENTS_FOR_EVALUATION
    )

    if review_count >= CONFIDENCE_HIGH_MIN_REVIEWS:
        max_confidence = "High"
    elif review_count >= CONFIDENCE_MEDIUM_MIN_REVIEWS:
        max_confidence = "Medium"
    elif review_count >= MIN_REVIEWS_FOR_EVALUATION:
        max_confidence = "Low"
    else:
        max_confidence = "N/A"

    return SufficiencyResult(
        is_sufficient=is_sufficient,
        max_confidence=max_confidence,
        review_count=review_count,
        placement_count=placement_count,
    )


def _step4_integrity_checks(data: RawDataPackage) -> IntegrityResult:
    """Step 4: Run all five integrity checks."""
    return run_all_integrity_checks(data)


def _step7_store_profile(
    trigger, data, corrected, integrity, weighted, llm_response, eval_log,
) -> TrustProfile:
    """Step 7: Build, validate, and store the trust profile."""
    now = datetime.now(timezone.utc)
    previous_tier = None
    if data.previous_profile:
        previous_tier = data.previous_profile.get("trust_tier")

    # Build signal summary
    signal_summary = _build_signal_summary(data, integrity)

    # Build audience summaries
    audience_raw = corrected.audience_summaries
    audience = AudienceSummaries(
        job_seeker=audience_raw.get("job_seeker", "Assessment pending."),
        hr_consultant=audience_raw.get("hr_consultant", "Assessment pending."),
        admin=audience_raw.get("admin", "Assessment pending."),
        licensing=audience_raw.get("licensing", "Assessment pending."),
    )

    # Determine tier change note
    tier_change_note = None
    if previous_tier and previous_tier != corrected.trust_tier:
        tier_change_note = corrected.tier_change_note or (
            f"Tier changed from {previous_tier} to {corrected.trust_tier}."
        )

    profile = TrustProfile(
        agency_id=trigger.agency_id,
        trust_tier=corrected.trust_tier,
        confidence_level=corrected.confidence_level,
        key_strengths=corrected.key_strengths,
        key_concerns=corrected.key_concerns,
        integrity_flags=integrity.flags,
        signal_summary=signal_summary,
        explanation=corrected.explanation,
        audience_summaries=audience,
        previous_tier=previous_tier,
        tier_change_note=tier_change_note,
        evaluated_at=now,
        evaluation_trigger=trigger.trigger_type,
        data_window_start=_earliest_data_date(data),
        llm_model_version=get_settings().llm_model,
    )

    # Write to database
    try:
        profile_dict = profile.model_dump(mode="json")
        # Remove None id for upsert
        profile_dict.pop("id", None)
        upsert_trust_profile(profile_dict)
    except Exception as exc:
        logger.error(f"Profile storage failed: {exc}")

    # Write audit log
    try:
        audit = AuditLogEntry(
            agency_id=trigger.agency_id,
            evaluation_trigger=trigger.trigger_type,
            triggered_by=trigger.requestor_id,
            raw_signal_snapshot={"review_count": len(data.reviews), "placement_count": len(data.placements)},
            integrity_checks_log={c.check_id: c.model_dump() for c in integrity.checks},
            weighted_signals={s.signal_name: s.final_weight for s in weighted.signals},
            llm_prompt_hash=llm_response.prompt_hash,
            llm_response_raw=llm_response.content,
            final_trust_tier=profile.trust_tier,
            final_confidence=profile.confidence_level,
        )
        audit_dict = audit.model_dump(mode="json")
        audit_dict.pop("id", None)
        insert_audit_log(audit_dict)
    except Exception as exc:
        logger.error(f"Audit log insert failed: {exc}")

    return profile


# ─── Helper Functions ───────────────────────────────────────

def _handle_insufficient_data(
    trigger, data, sufficiency, eval_log, start_time,
) -> TrustProfileResponse:
    """Handle InsufficientData shortcut (skip Steps 4-6)."""
    now = datetime.now(timezone.utc)
    profile = TrustProfile(
        agency_id=trigger.agency_id,
        trust_tier="InsufficientData",
        confidence_level="N/A",
        key_strengths=[],
        key_concerns=[],
        integrity_flags=[],
        signal_summary=SignalSummary(
            total_review_count=len(data.reviews),
            total_placements=len(data.placements),
        ),
        explanation=(
            f"This agency currently has {len(data.reviews)} reviews and "
            f"{len(data.placements)} placement records. A reliable trust "
            f"assessment requires a minimum of {MIN_REVIEWS_FOR_EVALUATION} "
            f"reviews or {MIN_PLACEMENTS_FOR_EVALUATION} placements. "
            f"Please check back when more data is available."
        ),
        audience_summaries=AudienceSummaries(
            job_seeker="This agency is new to the platform and doesn't have enough history for a trust assessment yet. Check back later when more reviews and placement data are available.",
            hr_consultant="Insufficient platform data for a trust assessment. Continue building your track record through verified placements and candidate feedback to receive a trust profile.",
            admin=f"Agency has {len(data.reviews)} reviews and {len(data.placements)} placements. Below minimum thresholds for evaluation. No integrity checks run.",
            licensing=f"REVIEW REQUIRED — Insufficient data for trust assessment. {len(data.reviews)} reviews, {len(data.placements)} placements. Minimum thresholds not met.",
        ),
        evaluated_at=now,
        evaluation_trigger=trigger.trigger_type,
        llm_model_version="none — insufficient data",
    )

    eval_log.final_tier = "InsufficientData"
    eval_log.confidence_level = "N/A"
    eval_log.duration_ms = _elapsed_ms(start_time)
    _log_evaluation(eval_log)

    return format_response_for_role(profile, trigger.requestor_role)


def _fallback_to_cache(trigger, eval_log, start_time, error_detail):
    """Serve stale cache on pipeline failure (PRD §11)."""
    stale = get_stale_cache_if_available(trigger.agency_id)
    eval_log.error = {"code": "PIPELINE_FAILURE", "message": error_detail}
    eval_log.duration_ms = _elapsed_ms(start_time)
    _log_evaluation(eval_log)

    if stale:
        logger.info("Serving stale cached profile after failure")
        profile = _dict_to_trust_profile(stale)
        response = format_response_for_role(profile, trigger.requestor_role)
        response.data_is_stale = True
        return response

    # No cache available — return minimal error response
    from utils.error_handler import LLMError
    raise LLMError(detail=f"Evaluation failed and no cache available: {error_detail}")


def _build_signal_summary(data, integrity) -> SignalSummary:
    """Build the signal summary from raw data."""
    now = datetime.now(timezone.utc)
    cutoff_30d = now - timedelta(days=30)
    cutoff_90d = now - timedelta(days=90)

    reviews_30d = [r for r in data.reviews if _to_utc(r.created_at) >= cutoff_30d]
    reviews_90d = [r for r in data.reviews if _to_utc(r.created_at) >= cutoff_90d]
    all_ratings = [r.rating for r in data.reviews]
    ratings_30d = [r.rating for r in reviews_30d]
    successful = sum(1 for p in data.placements if p.outcome == "successful")
    total_pl = len(data.placements)
    feedback = [f.score for f in data.feedback_ratings]

    tenure = 0
    if data.agency_meta.registration_date:
        tenure = (now - _to_utc(data.agency_meta.registration_date)).days

    return SignalSummary(
        total_review_count=len(data.reviews),
        reviews_last_30d=len(reviews_30d),
        reviews_last_90d=len(reviews_90d),
        avg_star_rating_all_time=round(sum(all_ratings) / len(all_ratings), 2) if all_ratings else None,
        avg_star_rating_30d=round(sum(ratings_30d) / len(ratings_30d), 2) if ratings_30d else None,
        total_placements=total_pl,
        successful_placements=successful,
        placement_rate=round(successful / total_pl, 3) if total_pl > 0 else None,
        avg_feedback_score=round(sum(feedback) / len(feedback), 2) if feedback else None,
        agency_tenure_days=tenure,
        anomalies_detected=integrity.any_flag,
        anomaly_count=len(integrity.flags),
    )


def _dict_to_trust_profile(data: dict) -> TrustProfile:
    """Convert a cached dict back to a TrustProfile model."""
    # Handle nested objects that may be dicts
    audience = data.get("audience_summaries", {})
    if isinstance(audience, dict) and not isinstance(audience, AudienceSummaries):
        audience = AudienceSummaries(**audience)

    signal = data.get("signal_summary", {})
    if isinstance(signal, dict) and not isinstance(signal, SignalSummary):
        signal = SignalSummary(**signal)

    return TrustProfile(
        id=data.get("id"),
        agency_id=data["agency_id"],
        trust_tier=data["trust_tier"],
        confidence_level=data["confidence_level"],
        key_strengths=data.get("key_strengths", []),
        key_concerns=data.get("key_concerns", []),
        integrity_flags=data.get("integrity_flags", []),
        signal_summary=signal,
        explanation=data.get("explanation", ""),
        audience_summaries=audience,
        previous_tier=data.get("previous_tier"),
        tier_change_note=data.get("tier_change_note"),
        evaluated_at=data.get("evaluated_at", datetime.now(timezone.utc)),
        evaluation_trigger=data.get("evaluation_trigger", "ON_DEMAND"),
        llm_model_version=data.get("llm_model_version", ""),
    )


def _earliest_data_date(data: RawDataPackage) -> Optional[datetime]:
    """Find the earliest timestamp across all data."""
    dates = []
    if data.reviews:
        dates.append(min(r.created_at for r in data.reviews))
    if data.placements:
        dates.append(min(p.created_at for p in data.placements))
    return min(dates) if dates else None


def _to_utc(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware in UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _elapsed_ms(start: float) -> int:
    """Calculate elapsed milliseconds since start."""
    return int((time.time() - start) * 1000)


def _log_evaluation(log: EvaluationLog) -> None:
    """Write structured evaluation log (PRD §12.2)."""
    logger.info(
        "Evaluation complete",
        extra={"extra_data": log.model_dump()},
    )
