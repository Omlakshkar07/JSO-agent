"""
parser.py
─────────────────────────────────────────────
PURPOSE:
  Defensively parse all LLM JSON responses into typed models.
  Never crashes on unexpected output — returns error state instead.

RESPONSIBILITIES:
  - parse_sentiment_response() → list of sentiment classifications
  - parse_trust_profile_response() → RawProfileDraft
  - Handle malformed JSON, missing fields, extra fields

NOT RESPONSIBLE FOR:
  - Calling the LLM (see client.py)
  - Prompt construction (see prompts.py)
  - Business validation of parsed content (see validators.py)

DEPENDENCIES:
  - models.internal: RawProfileDraft
  - utils.logger: for logging parse failures

USED BY:
  - agent/signal_auditor.py (sentiment parse)
  - agent/trust_reasoner.py (profile parse)
─────────────────────────────────────────────
"""

import json
import re
from typing import Optional

from models.internal import RawProfileDraft
from utils.logger import get_logger
from utils.error_handler import LLMParseError

logger = get_logger("llm.parser")


def _extract_json_from_text(text: str) -> str:
    """
    Extract JSON from LLM text that may contain markdown fences or preamble.

    Tries multiple strategies:
    1. Direct parse (text is already valid JSON)
    2. Strip markdown code fences
    3. Find first { or [ and last } or ]
    """
    text = text.strip()

    # Strategy 1: direct parse attempt
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip markdown fences
    fence_pattern = r"```(?:json)?\s*\n?(.*?)\n?\s*```"
    match = re.search(fence_pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Strategy 3: find JSON boundaries
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start_idx = text.find(start_char)
        end_idx = text.rfind(end_char)
        if start_idx != -1 and end_idx > start_idx:
            return text[start_idx:end_idx + 1]

    return text


def parse_sentiment_response(
    raw_text: str,
) -> list[dict]:
    """
    Parse the LLM sentiment classification response.

    Expected format: [{"review_id": "...", "sentiment": "POSITIVE"}]
    Returns empty list on parse failure — never crashes.

    Args:
        raw_text: Raw text from the LLM response.

    Returns:
        List of dicts with 'review_id' and 'sentiment' keys.
        Empty list if parsing fails.
    """
    try:
        cleaned = _extract_json_from_text(raw_text)
        parsed = json.loads(cleaned)

        if not isinstance(parsed, list):
            logger.warning("Sentiment response is not a list")
            return []

        # Validate each item has required fields
        validated = []
        for item in parsed:
            if "review_id" in item and "sentiment" in item:
                sentiment = item["sentiment"].upper()
                if sentiment in ("POSITIVE", "NEGATIVE", "NEUTRAL"):
                    validated.append({
                        "review_id": str(item["review_id"]),
                        "sentiment": sentiment,
                    })

        return validated

    except (json.JSONDecodeError, AttributeError) as exc:
        logger.warning(
            "Failed to parse sentiment response",
            extra={"extra_data": {"error": str(exc)}},
        )
        return []


def parse_trust_profile_response(
    raw_text: str,
) -> RawProfileDraft:
    """
    Parse the LLM trust synthesis response into a RawProfileDraft.

    Handles missing fields gracefully by using defaults.
    Never crashes — returns a draft with whatever was parseable.

    Args:
        raw_text: Raw text from the LLM response.

    Returns:
        RawProfileDraft with parsed fields (may have defaults for missing data).

    Raises:
        LLMParseError: If the response is completely unparseable JSON.
    """
    try:
        cleaned = _extract_json_from_text(raw_text)
        parsed = json.loads(cleaned)

        if not isinstance(parsed, dict):
            raise LLMParseError("Trust profile response is not a JSON object")

        # Extract audience_summaries defensively
        audience = parsed.get("audience_summaries", {})
        if not isinstance(audience, dict):
            audience = {}

        return RawProfileDraft(
            trust_tier=str(parsed.get("trust_tier", "")),
            confidence_level=str(parsed.get("confidence_level", "")),
            key_strengths=_safe_list(parsed.get("key_strengths", [])),
            key_concerns=_safe_list(parsed.get("key_concerns", [])),
            explanation=str(parsed.get("explanation", "")),
            audience_summaries=audience,
            tier_change_note=parsed.get("tier_change_note"),
        )

    except json.JSONDecodeError as exc:
        logger.error(
            "Failed to parse trust profile JSON",
            extra={"extra_data": {
                "error": str(exc),
                "raw_text_preview": raw_text[:200],
            }},
        )
        raise LLMParseError(
            detail=f"LLM returned unparseable JSON: {str(exc)}"
        )


def _safe_list(value: object, max_items: int = 3) -> list[str]:
    """Convert a value to a list of strings, capped at max_items."""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value[:max_items]]
