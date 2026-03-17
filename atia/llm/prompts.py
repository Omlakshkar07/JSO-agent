"""
prompts.py
─────────────────────────────────────────────
PURPOSE:
  ALL LLM prompts live here and ONLY here.
  Prompts are functions that take parameters and return
  (system_prompt, user_prompt) tuples.

RESPONSIBILITIES:
  - Sub-Agent A sentiment check prompt (PRD §6.4)
  - Sub-Agent B trust synthesis prompt (PRD §6.4)
  - No f-strings or prompt fragments in other files

NOT RESPONSIBLE FOR:
  - Sending prompts to the LLM (see client.py)
  - Parsing LLM responses (see parser.py)

DEPENDENCIES:
  - None (pure string construction)

USED BY:
  - agent/signal_auditor.py (sentiment check)
  - agent/trust_reasoner.py (trust synthesis)
─────────────────────────────────────────────
"""

import json
from typing import Optional


def build_sentiment_check_prompt(
    reviews_json: list[dict],
) -> tuple[str, str]:
    """
    Build the prompt for Sub-Agent A's sentiment-rating mismatch check.

    This prompt asks the LLM to classify the sentiment of each review's
    written text independently of its star rating. Used in Step 4E to
    detect reviews where the text contradicts the rating.

    Args:
        reviews_json: List of dicts with 'review_id' and 'review_text' keys.
                     Reviewer names/IDs are already stripped for PII safety.

    Returns:
        Tuple of (system_prompt, user_prompt) strings.

    Example:
        >>> sys, usr = build_sentiment_check_prompt([
        ...     {"review_id": "r1", "review_text": "Terrible experience"}
        ... ])
    """
    system_prompt = (
        "You are a signal integrity auditor for a recruitment platform.\n"
        "You receive a list of written reviews. For each review, classify\n"
        "the sentiment as POSITIVE, NEGATIVE, or NEUTRAL based solely on\n"
        "the written text, ignoring the star rating provided.\n"
        "Return ONLY a JSON array. No explanation. No preamble.\n"
        'Format: [{"review_id": "...", "sentiment": "POSITIVE"}]'
    )

    user_prompt = f"Reviews:\n{json.dumps(reviews_json, indent=2)}"

    return system_prompt, user_prompt


def build_trust_synthesis_prompt(
    agency_id: str,
    weighted_signals_json: dict,
    integrity_flags_json: list[dict],
    sufficiency_json: dict,
    previous_profile_json: Optional[dict],
) -> tuple[str, str]:
    """
    Build the prompt for Sub-Agent B's trust profile synthesis.

    This is the main reasoning prompt. The LLM receives all weighted
    signals, integrity results, and previous profile context. It
    produces a complete TrustProfile JSON object.

    Args:
        agency_id: UUID of the agency being evaluated.
        weighted_signals_json: Output of the weighting engine.
        integrity_flags_json: All active integrity flags.
        sufficiency_json: Data sufficiency result.
        previous_profile_json: Previous trust profile or None.

    Returns:
        Tuple of (system_prompt, user_prompt) strings.
    """
    system_prompt = (
        "You are the Trust Reasoning Engine for the JSO recruitment platform.\n"
        "Your job is to produce a structured trust assessment of a recruitment\n"
        "agency based ONLY on the evidence provided. You must:\n"
        "\n"
        "1. NEVER invent data not present in the input.\n"
        "2. NEVER name individual reviewers.\n"
        "3. ALWAYS cite at least one specific data signal in your explanation.\n"
        "4. ALWAYS acknowledge uncertainty when confidence is not High.\n"
        "5. Write in plain English — no jargon, no technical terms.\n"
        "\n"
        "Return ONLY valid JSON matching this exact schema:\n"
        "{\n"
        '  "trust_tier": "High|Medium|Low|UnderReview|InsufficientData",\n'
        '  "confidence_level": "High|Medium|Low|N/A",\n'
        '  "key_strengths": ["string", "string", "string"],\n'
        '  "key_concerns": ["string", "string", "string"],\n'
        '  "explanation": "50-150 word plain-language reasoning",\n'
        '  "audience_summaries": {\n'
        '    "job_seeker": "40-80 words. Plain English. Empathetic.",\n'
        '    "hr_consultant": "60-100 words. Professional. Benchmarked.",\n'
        '    "admin": "100-200 words. Technical. Complete.",\n'
        '    "licensing": "60-100 words. Formal. Decision-ready."\n'
        "  },\n"
        '  "tier_change_note": "string or null"\n'
        "}\n"
        "\n"
        "No explanation outside the JSON. No markdown fences."
    )

    user_prompt = (
        f"Agency ID: {agency_id}\n\n"
        f"Weighted signal set:\n"
        f"{json.dumps(weighted_signals_json, indent=2)}\n\n"
        f"Integrity flags:\n"
        f"{json.dumps(integrity_flags_json, indent=2)}\n\n"
        f"Sufficiency result:\n"
        f"{json.dumps(sufficiency_json, indent=2)}\n\n"
        f"Previous profile:\n"
        f"{json.dumps(previous_profile_json, indent=2)}\n\n"
        f"Produce the complete TrustProfile JSON object now."
    )

    return system_prompt, user_prompt
