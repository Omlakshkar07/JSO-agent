"""
cache_manager.py
─────────────────────────────────────────────
PURPOSE:
  Manages trust profile caching logic (PRD §FR-005).
  A cached profile is served without re-running the LLM
  if it is less than 24 hours old AND no data events
  have occurred since the last evaluation.

RESPONSIBILITIES:
  - Check if a cached profile is valid
  - Retrieve cached profiles
  - Determine if cache should be bypassed

NOT RESPONSIBLE FOR:
  - Writing profiles to DB (see agency_queries.py)
  - Evaluation logic (see orchestrator.py)

DEPENDENCIES:
  - data.supabase_client: database access
  - config.constants: CACHE_TTL_HOURS
  - utils.logger: cache hit/miss logging

USED BY:
  - agent/orchestrator.py (Step 1 cache check)
─────────────────────────────────────────────
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

from data.supabase_client import get_supabase_client
from config.constants import CACHE_TTL_HOURS, STALE_CACHE_MAX_HOURS
from utils.logger import get_logger

logger = get_logger("memory.cache_manager")


def get_cached_profile(agency_id: str) -> Optional[dict]:
    """
    Retrieve a cached trust profile if one exists.

    Does NOT check validity — use is_cache_valid() for that.

    Args:
        agency_id: UUID of the agency.

    Returns:
        The cached profile as a dict, or None if not found.
    """
    try:
        client = get_supabase_client()
        result = (
            client.table("trust_profiles")
            .select("*")
            .eq("agency_id", agency_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as exc:
        logger.warning(
            "Cache lookup failed",
            extra={"extra_data": {"agency_id": agency_id, "error": str(exc)}},
        )
        return None


def is_cache_valid(
    cached_profile: dict,
    agency_id: str,
) -> bool:
    """
    Check if a cached profile is fresh enough to serve directly.

    A cache is valid when:
    1. The profile is less than CACHE_TTL_HOURS old (24h)
    2. No new reviews or placement updates since the evaluation

    Args:
        cached_profile: The cached trust profile dict.
        agency_id: UUID of the agency.

    Returns:
        True if the cache can be served, False if re-evaluation needed.
    """
    evaluated_at_str = cached_profile.get("evaluated_at")
    if not evaluated_at_str:
        return False

    evaluated_at = _parse_timestamp(evaluated_at_str)
    if not evaluated_at:
        return False

    # Check 1: is the profile less than 24 hours old?
    age = datetime.now(timezone.utc) - evaluated_at
    if age > timedelta(hours=CACHE_TTL_HOURS):
        logger.info(
            "Cache expired (age check)",
            extra={"extra_data": {"agency_id": agency_id, "age_hours": age.total_seconds() / 3600}},
        )
        return False

    # Check 2: any new data events since evaluation?
    if _has_new_events_since(agency_id, evaluated_at):
        logger.info(
            "Cache invalidated (new data events)",
            extra={"extra_data": {"agency_id": agency_id}},
        )
        return False

    return True


def get_stale_cache_if_available(agency_id: str) -> Optional[dict]:
    """
    Get a stale cached profile for fallback during errors.

    Serves profiles up to STALE_CACHE_MAX_HOURS (72h) old.
    Used when the evaluation pipeline fails and we need
    something to show the user rather than an error.

    Args:
        agency_id: UUID of the agency.

    Returns:
        The stale profile dict with 'data_is_stale' flag, or None.
    """
    cached = get_cached_profile(agency_id)
    if not cached:
        return None

    evaluated_at_str = cached.get("evaluated_at")
    if not evaluated_at_str:
        return None

    evaluated_at = _parse_timestamp(evaluated_at_str)
    if not evaluated_at:
        return None

    age = datetime.now(timezone.utc) - evaluated_at
    if age > timedelta(hours=STALE_CACHE_MAX_HOURS):
        return None

    cached["data_is_stale"] = True
    return cached


def _has_new_events_since(agency_id: str, since: datetime) -> bool:
    """Check if new reviews or placements exist since the given timestamp."""
    try:
        client = get_supabase_client()
        since_iso = since.isoformat()

        # Check for new reviews
        reviews = (
            client.table("reviews")
            .select("id", count="exact")
            .eq("agency_id", agency_id)
            .gt("created_at", since_iso)
            .execute()
        )
        if reviews.count and reviews.count > 0:
            return True

        # Check for updated placements
        placements = (
            client.table("placements")
            .select("id", count="exact")
            .eq("agency_id", agency_id)
            .gt("created_at", since_iso)
            .execute()
        )
        if placements.count and placements.count > 0:
            return True

        return False

    except Exception as exc:
        logger.warning(
            "Event check failed, assuming cache invalid",
            extra={"extra_data": {"error": str(exc)}},
        )
        # Fail open: if we can't check, assume cache is invalid
        return True


def _parse_timestamp(value: object) -> Optional[datetime]:
    """Parse a timestamp string or datetime object."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return None

    return None
