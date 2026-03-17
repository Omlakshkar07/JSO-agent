"""
validators.py
─────────────────────────────────────────────
PURPOSE:
  Post-LLM validation of trust profiles. Enforces the
  deterministic rules from PRD §6.3 that the LLM must
  not violate, regardless of what it generates.

RESPONSIBILITIES:
  - Validate trust tier is one of five allowed values
  - Enforce: P0 flag → tier MUST be UnderReview
  - Enforce: InsufficientData → confidence MUST be N/A
  - Enforce: confidence ceiling based on data volume
  - Validate explanation meets minimum word count

NOT RESPONSIBLE FOR:
  - Input validation (Pydantic handles that)
  - Calling the LLM or parsing its output

DEPENDENCIES:
  - config.constants: tier/confidence enums, thresholds
  - models.internal: SufficiencyResult, IntegrityResult
  - utils.logger: for logging overrides

USED BY:
  - agent/orchestrator.py (Step 7 validation)
─────────────────────────────────────────────
"""

from models.internal import (
    RawProfileDraft,
    SufficiencyResult,
    IntegrityResult,
)
from config.constants import (
    TRUST_TIERS,
    CONFIDENCE_LEVELS,
    EXPLANATION_MIN_WORDS,
    SEVERITY_P0,
)
from utils.logger import get_logger

logger = get_logger("utils.validators")


def validate_and_correct_profile(
    draft: RawProfileDraft,
    sufficiency: SufficiencyResult,
    integrity: IntegrityResult,
) -> RawProfileDraft:
    """
    Validate a trust profile draft against deterministic rules.

    The LLM is not trusted to follow rules perfectly. This function
    overrides the LLM's output when it violates PRD §6.3 rules.
    Returns a corrected copy — does not modify the input.

    Args:
        draft: The raw profile from the LLM.
        sufficiency: Data sufficiency result from Step 3.
        integrity: Integrity check results from Step 4.

    Returns:
        A corrected RawProfileDraft with all rules enforced.
    """
    corrected = draft.model_copy()

    corrected = _enforce_valid_tier(corrected)
    corrected = _enforce_valid_confidence(corrected)
    corrected = _enforce_insufficient_data_rules(corrected, sufficiency)
    corrected = _enforce_integrity_rules(corrected, integrity)
    corrected = _enforce_confidence_ceiling(corrected, sufficiency)
    corrected = _enforce_explanation_quality(corrected)
    corrected = _enforce_list_limits(corrected)

    return corrected


def _enforce_valid_tier(draft: RawProfileDraft) -> RawProfileDraft:
    """Reject invalid tier values — default to UnderReview."""
    if draft.trust_tier not in TRUST_TIERS:
        logger.warning(
            "LLM produced invalid tier, defaulting to UnderReview",
            extra={"extra_data": {"invalid_tier": draft.trust_tier}},
        )
        draft.trust_tier = "UnderReview"
    return draft


def _enforce_valid_confidence(draft: RawProfileDraft) -> RawProfileDraft:
    """Reject invalid confidence values — default to Low."""
    if draft.confidence_level not in CONFIDENCE_LEVELS:
        logger.warning(
            "LLM produced invalid confidence, defaulting to Low",
            extra={"extra_data": {"invalid_confidence": draft.confidence_level}},
        )
        draft.confidence_level = "Low"
    return draft


def _enforce_insufficient_data_rules(
    draft: RawProfileDraft,
    sufficiency: SufficiencyResult,
) -> RawProfileDraft:
    """
    PRD §FR-021: InsufficientData → confidence = N/A.
    Also prevents any other tier when data is insufficient.
    """
    if not sufficiency.is_sufficient:
        if draft.trust_tier != "InsufficientData":
            logger.info("Forcing tier to InsufficientData (data below threshold)")
            draft.trust_tier = "InsufficientData"
        draft.confidence_level = "N/A"
    return draft


def _enforce_integrity_rules(
    draft: RawProfileDraft,
    integrity: IntegrityResult,
) -> RawProfileDraft:
    """
    PRD §FR-022: Any P0 flag → tier MUST be UnderReview.
    The LLM sometimes ignores this constraint.
    """
    if integrity.any_p0_flag and draft.trust_tier != "UnderReview":
        logger.warning(
            "P0 flag active but LLM assigned non-UnderReview tier — overriding",
            extra={"extra_data": {
                "llm_tier": draft.trust_tier,
                "forced_tier": "UnderReview",
            }},
        )
        draft.trust_tier = "UnderReview"

    # PRD §FR-023: confidence reduced by at least one level with any flag
    if integrity.any_flag and draft.confidence_level == "High":
        draft.confidence_level = "Medium"

    return draft


def _enforce_confidence_ceiling(
    draft: RawProfileDraft,
    sufficiency: SufficiencyResult,
) -> RawProfileDraft:
    """
    Cap confidence based on data volume (PRD §6.2 Step 3).
    """
    ceiling = sufficiency.max_confidence
    level_order = {"N/A": 0, "Low": 1, "Medium": 2, "High": 3}

    current_rank = level_order.get(draft.confidence_level, 0)
    ceiling_rank = level_order.get(ceiling, 0)

    if current_rank > ceiling_rank:
        logger.info(
            f"Capping confidence from {draft.confidence_level} to {ceiling}",
        )
        draft.confidence_level = ceiling

    return draft


def _enforce_explanation_quality(draft: RawProfileDraft) -> RawProfileDraft:
    """Ensure explanation meets minimum word count."""
    word_count = len(draft.explanation.split())
    if word_count < EXPLANATION_MIN_WORDS and draft.explanation:
        logger.warning(
            f"Explanation too short ({word_count} words, min {EXPLANATION_MIN_WORDS})",
        )
        # We don't fix this — just log it. The LLM's explanation is
        # still better than a fabricated one.
    return draft


def _enforce_list_limits(draft: RawProfileDraft) -> RawProfileDraft:
    """Cap strengths and concerns to 3 items max."""
    draft.key_strengths = draft.key_strengths[:3]
    draft.key_concerns = draft.key_concerns[:3]
    return draft
