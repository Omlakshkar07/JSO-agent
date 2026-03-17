"""
responder.py
─────────────────────────────────────────────
PURPOSE:
  Audience-aware response formatting (PRD §6.2 Step 8).
  Selects the appropriate summary and fields based on
  the requestor's role.

RESPONSIBILITIES:
  - Format TrustProfile for each audience type
  - Add staleness indicators
  - Add benchmark data for HR consultants
  - Add licensing threshold pass/fail indicators

NOT RESPONSIBLE FOR:
  - Profile creation or validation
  - Database queries

DEPENDENCIES:
  - models.outputs: TrustProfile, TrustProfileResponse
  - config.constants: LICENSING_PASS_TIERS

USED BY:
  - agent/orchestrator.py (Step 8)
  - api/routes.py (response formatting)
─────────────────────────────────────────────
"""

from datetime import datetime, timezone, timedelta

from models.outputs import TrustProfile, TrustProfileResponse
from config.constants import CACHE_TTL_HOURS, LICENSING_PASS_TIERS
from utils.logger import get_logger

logger = get_logger("agent.responder")


def format_response_for_role(
    profile: TrustProfile,
    requestor_role: str,
) -> TrustProfileResponse:
    """
    Format a trust profile for the requesting user's role.

    Each role sees different fields and a different summary
    as defined in PRD §6.2 Step 8 and §6.5.

    Args:
        profile: The complete TrustProfile.
        requestor_role: One of job_seeker, hr_consultant, admin, licensing.

    Returns:
        A TrustProfileResponse tailored to the role.
    """
    summary = _select_summary(profile, requestor_role)
    is_stale = _check_staleness(profile)

    response = TrustProfileResponse(
        agency_id=profile.agency_id,
        trust_tier=profile.trust_tier,
        confidence_level=profile.confidence_level,
        key_strengths=profile.key_strengths,
        key_concerns=profile.key_concerns,
        integrity_flags=profile.integrity_flags if requestor_role in ("admin", "licensing") else [],
        summary=summary,
        tier_change_note=profile.tier_change_note,
        evaluated_at=profile.evaluated_at,
        data_is_stale=is_stale,
    )

    # Job seekers see integrity flags only as disclosure text in summary
    # (not as structured flag objects) — PRD §FR-012
    if requestor_role == "job_seeker" and profile.integrity_flags:
        response.integrity_flags = []

    return response


def _select_summary(profile: TrustProfile, role: str) -> str:
    """Select the audience-appropriate summary string."""
    summaries = profile.audience_summaries
    role_map = {
        "job_seeker": summaries.job_seeker,
        "hr_consultant": summaries.hr_consultant,
        "admin": summaries.admin,
        "licensing": _enhance_licensing_summary(summaries.licensing, profile),
    }
    return role_map.get(role, summaries.job_seeker)


def _enhance_licensing_summary(base_summary: str, profile: TrustProfile) -> str:
    """Add PASS/FAIL indicators to the licensing summary."""
    tier_status = "PASS" if profile.trust_tier in LICENSING_PASS_TIERS else "FAIL"
    if profile.trust_tier == "InsufficientData":
        tier_status = "REVIEW REQUIRED"
    if profile.trust_tier == "UnderReview":
        tier_status = "REVIEW REQUIRED"

    return f"[Licensing Status: {tier_status}] {base_summary}"


def _check_staleness(profile: TrustProfile) -> bool:
    """Check if the profile is older than the cache TTL."""
    if not profile.evaluated_at:
        return True
    age = datetime.now(timezone.utc) - profile.evaluated_at.replace(
        tzinfo=timezone.utc
    ) if profile.evaluated_at.tzinfo is None else datetime.now(timezone.utc) - profile.evaluated_at
    return age > timedelta(hours=CACHE_TTL_HOURS)
