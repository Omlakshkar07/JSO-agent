"""
agency_queries.py
─────────────────────────────────────────────
PURPOSE:
  All Supabase queries for agency data retrieval and
  trust profile storage. Maps to PRD §6.2 Step 2 queries
  (Q1-Q6) plus write operations for Step 7.

RESPONSIBILITIES:
  - Fetch reviews, placements, feedback, reviewer metadata
  - Fetch existing trust profiles and agency metadata
  - Upsert trust profiles
  - Insert immutable audit log entries
  - Fetch anomaly queue data

NOT RESPONSIBLE FOR:
  - Business logic or data interpretation
  - Cache decisions (see cache_manager.py)

DEPENDENCIES:
  - data.supabase_client: database connection
  - models.inputs: raw data shapes
  - utils.logger: query logging
  - utils.error_handler: DataRetrievalError

USED BY:
  - agent/orchestrator.py (data retrieval + storage)
  - memory/cache_manager.py (profile queries)
  - api/routes.py (audit trail, anomaly queue)
─────────────────────────────────────────────
"""

from typing import Optional

from data.supabase_client import get_supabase_client
from models.inputs import (
    RawReview,
    RawPlacement,
    RawFeedback,
    ReviewerMetadata,
    AgencyMeta,
    RawDataPackage,
)
from utils.logger import get_logger
from utils.error_handler import DataRetrievalError

logger = get_logger("data.agency_queries")


def fetch_raw_data_package(agency_id: str) -> RawDataPackage:
    """
    Fetch all data needed for an agency evaluation (PRD §6.2 Step 2).

    Runs queries Q1-Q6 and assembles them into a RawDataPackage.
    If any query fails, raises DataRetrievalError — the orchestrator
    will fall back to cached data.

    Args:
        agency_id: UUID of the agency to evaluate.

    Returns:
        Complete RawDataPackage with all query results.

    Raises:
        DataRetrievalError: If any database query fails.
    """
    try:
        agency_meta = _fetch_agency_meta(agency_id)
        reviews = _fetch_reviews(agency_id)
        placements = _fetch_placements(agency_id)
        feedback = _fetch_feedback_ratings(agency_id)
        reviewer_ids = [r.reviewer_id for r in reviews]
        reviewer_meta = _fetch_reviewer_metadata(reviewer_ids)
        previous = _fetch_current_trust_profile(agency_id)

        return RawDataPackage(
            agency_id=agency_id,
            agency_meta=agency_meta,
            reviews=reviews,
            placements=placements,
            feedback_ratings=feedback,
            reviewer_metadata=reviewer_meta,
            previous_profile=previous,
        )

    except DataRetrievalError:
        raise
    except Exception as exc:
        logger.error(
            "Data retrieval failed",
            extra={"extra_data": {"agency_id": agency_id, "error": str(exc)}},
        )
        raise DataRetrievalError(detail=f"Failed to fetch data for agency {agency_id}: {exc}")


def _fetch_agency_meta(agency_id: str) -> AgencyMeta:
    """Q6: Fetch agency metadata."""
    client = get_supabase_client()
    result = (
        client.table("agencies")
        .select("id, name, registration_date, is_active")
        .eq("id", agency_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise DataRetrievalError(f"Agency {agency_id} not found")
    return AgencyMeta(**result.data[0])


def _fetch_reviews(agency_id: str) -> list[RawReview]:
    """Q1: Fetch all reviews for an agency, newest first."""
    client = get_supabase_client()
    result = (
        client.table("reviews")
        .select("id, agency_id, reviewer_id, rating, review_text, created_at")
        .eq("agency_id", agency_id)
        .order("created_at", desc=True)
        .execute()
    )
    return [RawReview(**row) for row in (result.data or [])]


def _fetch_placements(agency_id: str) -> list[RawPlacement]:
    """Q2: Fetch all placement records for an agency."""
    client = get_supabase_client()
    result = (
        client.table("placements")
        .select("id, agency_id, candidate_id, outcome, placement_source, created_at")
        .eq("agency_id", agency_id)
        .execute()
    )
    return [RawPlacement(**row) for row in (result.data or [])]


def _fetch_feedback_ratings(agency_id: str) -> list[RawFeedback]:
    """Q3: Fetch all feedback ratings for an agency."""
    client = get_supabase_client()
    result = (
        client.table("feedback_ratings")
        .select("id, agency_id, score, created_at")
        .eq("agency_id", agency_id)
        .execute()
    )
    return [RawFeedback(**row) for row in (result.data or [])]


def _fetch_reviewer_metadata(reviewer_ids: list[str]) -> list[ReviewerMetadata]:
    """Q4: Fetch account age for reviewers."""
    if not reviewer_ids:
        return []

    client = get_supabase_client()
    # Deduplicate reviewer IDs
    unique_ids = list(set(reviewer_ids))
    result = (
        client.table("users")
        .select("id, account_age_days")
        .in_("id", unique_ids)
        .execute()
    )
    return [
        ReviewerMetadata(user_id=row["id"], account_age_days=row.get("account_age_days", 0))
        for row in (result.data or [])
    ]


def _fetch_current_trust_profile(agency_id: str) -> Optional[dict]:
    """Q5: Fetch the current trust profile if one exists."""
    client = get_supabase_client()
    result = (
        client.table("trust_profiles")
        .select("*")
        .eq("agency_id", agency_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def upsert_trust_profile(profile_data: dict) -> dict:
    """
    Write a trust profile to the database (upsert on agency_id).

    Args:
        profile_data: TrustProfile as a dict.

    Returns:
        The upserted record.

    Raises:
        DataRetrievalError: If the write fails.
    """
    try:
        client = get_supabase_client()
        result = (
            client.table("trust_profiles")
            .upsert(profile_data, on_conflict="agency_id")
            .execute()
        )
        logger.info(
            "Trust profile upserted",
            extra={"extra_data": {"agency_id": profile_data.get("agency_id")}},
        )
        return result.data[0] if result.data else profile_data
    except Exception as exc:
        raise DataRetrievalError(f"Failed to write trust profile: {exc}")


def insert_audit_log(entry_data: dict) -> dict:
    """
    Append an immutable audit log entry (PRD §7.3).

    This table is INSERT-only — no UPDATE, no DELETE.

    Args:
        entry_data: AuditLogEntry as a dict.

    Returns:
        The inserted record.

    Raises:
        DataRetrievalError: If the insert fails.
    """
    try:
        client = get_supabase_client()
        result = (
            client.table("evaluation_audit_log")
            .insert(entry_data)
            .execute()
        )
        return result.data[0] if result.data else entry_data
    except Exception as exc:
        logger.error(
            "Audit log insert failed",
            extra={"extra_data": {"error": str(exc)}},
        )
        raise DataRetrievalError(f"Failed to insert audit log: {exc}")


def fetch_audit_trail(agency_id: str) -> list[dict]:
    """Fetch all audit log entries for an agency, newest first."""
    client = get_supabase_client()
    result = (
        client.table("evaluation_audit_log")
        .select("*")
        .eq("agency_id", agency_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def fetch_anomaly_queue() -> list[dict]:
    """
    Fetch all agencies with active P0 integrity flags.

    Queries trust_profiles where integrity_flags contains
    any flag with severity P0.
    """
    client = get_supabase_client()
    result = (
        client.table("trust_profiles")
        .select("agency_id, integrity_flags, trust_tier, evaluated_at")
        .eq("trust_tier", "UnderReview")
        .order("evaluated_at", desc=True)
        .execute()
    )
    return result.data or []


def fetch_agency_name(agency_id: str) -> str:
    """Fetch just the agency name for display."""
    client = get_supabase_client()
    result = (
        client.table("agencies")
        .select("name")
        .eq("id", agency_id)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0].get("name", "Unknown Agency")
    return "Unknown Agency"


def fetch_trust_profile_history(agency_id: str) -> list[dict]:
    """Fetch trust tier change history from audit log."""
    client = get_supabase_client()
    result = (
        client.table("evaluation_audit_log")
        .select("created_at, final_trust_tier, final_confidence")
        .eq("agency_id", agency_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def fetch_all_agencies_with_profiles() -> list[dict]:
    """Fetch all agencies and their associated trust profiles."""
    try:
        client = get_supabase_client()
        result = (
            client.table("agencies")
            .select("id, name, registration_date, is_active, trust_profiles(*)")
            .execute()
        )
        
        agencies = []
        for row in (result.data or []):
            profiles = row.get("trust_profiles") or []
            if isinstance(profiles, list) and len(profiles) > 0:
                profile = profiles[0]
            elif isinstance(profiles, dict):
                profile = profiles
            else:
                profile = None
                
            agency = {
                "id": row["id"],
                "name": row["name"],
                "registration_date": row["registration_date"],
                "is_active": row["is_active"],
                "profile": profile
            }
            agencies.append(agency)
        return agencies
    except Exception as exc:
        logger.error(f"Failed to fetch agencies with profiles: {exc}")
        return []
