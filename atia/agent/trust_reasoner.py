"""
trust_reasoner.py
─────────────────────────────────────────────
PURPOSE:
  Sub-Agent B — Trust Profile Synthesis.
  Sends weighted signals to Claude for trust tier determination,
  confidence assessment, and audience-specific explanation
  generation (PRD §6.2 Step 6).

RESPONSIBILITIES:
  - Build LLM prompt with all evaluation context
  - Call Claude for trust synthesis
  - Parse LLM response into RawProfileDraft
  - Return draft for validation in Step 7

NOT RESPONSIBLE FOR:
  - Data retrieval or integrity checks (Sub-Agent A)
  - Post-LLM validation (see validators.py)
  - Final storage (see orchestrator.py)

DEPENDENCIES:
  - llm.prompts: prompt construction
  - llm.client: API communication
  - llm.parser: response parsing
  - models.internal: WeightedSignalSet, RawProfileDraft, etc.
  - utils.logger

USED BY:
  - agent/orchestrator.py (Step 6)
─────────────────────────────────────────────
"""

from typing import Optional

from llm.prompts import build_trust_synthesis_prompt
from llm.client import call_llm, LLMResponse
from llm.parser import parse_trust_profile_response
from models.internal import (
    WeightedSignalSet,
    SufficiencyResult,
    IntegrityResult,
    RawProfileDraft,
)
from utils.logger import get_logger

logger = get_logger("agent.trust_reasoner")


def synthesize_trust_profile(
    agency_id: str,
    weighted_signals: WeightedSignalSet,
    integrity: IntegrityResult,
    sufficiency: SufficiencyResult,
    previous_profile: Optional[dict],
) -> tuple[RawProfileDraft, LLMResponse]:
    """
    Run Sub-Agent B to produce a trust profile draft (PRD §6.2 Step 6).

    Sends all evaluation context to Claude and parses the response
    into a RawProfileDraft. The draft is NOT validated here — that
    happens in Step 7 via validators.py.

    Args:
        agency_id: UUID of the agency being evaluated.
        weighted_signals: Output of Step 5 (weighting engine).
        integrity: Output of Step 4 (integrity checks).
        sufficiency: Output of Step 3 (data sufficiency).
        previous_profile: Previous trust profile if one exists.

    Returns:
        Tuple of (RawProfileDraft, LLMResponse).
        The LLMResponse is returned for audit logging (prompt hash, raw text).

    Raises:
        LLMError: If the Claude API call fails after retries.
        LLMParseError: If the response cannot be parsed at all.
    """
    # Serialize data for the prompt
    signals_json = _serialize_signals(weighted_signals)
    flags_json = _serialize_flags(integrity)
    sufficiency_json = _serialize_sufficiency(sufficiency)

    system_prompt, user_prompt = build_trust_synthesis_prompt(
        agency_id=agency_id,
        weighted_signals_json=signals_json,
        integrity_flags_json=flags_json,
        sufficiency_json=sufficiency_json,
        previous_profile_json=previous_profile,
    )

    logger.info(
        "Calling LLM for trust synthesis",
        extra={"extra_data": {"agency_id": agency_id}},
    )

    llm_response = call_llm(system_prompt, user_prompt)
    draft = parse_trust_profile_response(llm_response.content)

    logger.info(
        "Trust synthesis complete",
        extra={"extra_data": {
            "agency_id": agency_id,
            "llm_tier": draft.trust_tier,
            "llm_confidence": draft.confidence_level,
        }},
    )

    return draft, llm_response


def _serialize_signals(signals: WeightedSignalSet) -> dict:
    """Serialize WeightedSignalSet for the LLM prompt."""
    return {
        "signals": [
            {
                "name": s.signal_name,
                "weight": s.final_weight,
                "integrity": s.integrity_annotation,
                "adjustments": s.adjustments_applied,
            }
            for s in signals.signals
        ],
        "aggregate_stats": {
            "avg_star_rating": signals.avg_star_rating,
            "avg_star_rating_30d": signals.avg_star_rating_30d,
            "placement_rate": signals.placement_rate,
            "placement_source": signals.placement_source,
            "avg_feedback_score": signals.avg_feedback_score,
            "recent_review_ratio": signals.recent_review_ratio,
        },
    }


def _serialize_flags(integrity: IntegrityResult) -> list[dict]:
    """Serialize integrity flags for the LLM prompt."""
    return [
        {
            "flag_id": f.flag_id,
            "severity": f.severity,
            "label": f.label,
            "description": f.description,
            "evidence": f.evidence_summary,
        }
        for f in integrity.flags
    ]


def _serialize_sufficiency(sufficiency: SufficiencyResult) -> dict:
    """Serialize sufficiency result for the LLM prompt."""
    return {
        "is_sufficient": sufficiency.is_sufficient,
        "max_confidence": sufficiency.max_confidence,
        "review_count": sufficiency.review_count,
        "placement_count": sufficiency.placement_count,
    }
