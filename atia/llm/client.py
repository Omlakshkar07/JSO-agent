"""
client.py
─────────────────────────────────────────────
PURPOSE:
  Single entry point for all LLM API communication.
  Handles retries, timeouts, rate limits, and error
  normalization. No other module calls Anthropic directly.

RESPONSIBILITIES:
  - call_llm() → send prompt, receive response
  - Retry once on failure (PRD §11)
  - Enforce timeout (default 30s)
  - Log every call: model, tokens, latency, success/failure

NOT RESPONSIBLE FOR:
  - Prompt construction (see prompts.py)
  - Response parsing (see parser.py)
  - Business logic of any kind

DEPENDENCIES:
  - anthropic: official SDK
  - config.settings: API key, model, timeout
  - utils.logger: structured logging

USED BY:
  - agent/signal_auditor.py (sentiment check)
  - agent/trust_reasoner.py (trust synthesis)
─────────────────────────────────────────────
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Optional

import anthropic

from config.settings import get_settings
from config.constants import LLM_MAX_RETRIES
from utils.logger import get_logger
from utils.error_handler import LLMError

logger = get_logger("llm.client")


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""

    content: str
    model: str
    input_tokens: int
    output_tokens: int
    prompt_hash: str
    latency_ms: int
    success: bool
    error: Optional[str] = None


def _compute_prompt_hash(system: str, user: str) -> str:
    """SHA-256 hash of prompt for audit reproducibility."""
    combined = f"{system}\n---\n{user}"
    return hashlib.sha256(combined.encode()).hexdigest()


def call_llm(
    system_prompt: str,
    user_prompt: str,
    max_tokens: Optional[int] = None,
) -> LLMResponse:
    """
    Send a prompt to Claude and return the structured response.

    Retries once on failure. Logs every call with model,
    token count, latency, and success/failure status.

    Args:
        system_prompt: The system instruction for Claude.
        user_prompt: The user message with data.
        max_tokens: Override default max tokens if needed.

    Returns:
        LLMResponse with content and metadata.

    Raises:
        LLMError: After all retries are exhausted.

    Example:
        >>> response = call_llm("You are a helper.", "What is 2+2?")
        >>> response.content  # "4"
    """
    settings = get_settings()
    prompt_hash = _compute_prompt_hash(system_prompt, user_prompt)
    tokens = max_tokens or settings.llm_max_tokens

    last_error: Optional[str] = None

    for attempt in range(1 + LLM_MAX_RETRIES):
        start_time = time.time()
        try:
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            response = client.messages.create(
                model=settings.llm_model,
                max_tokens=tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                timeout=settings.llm_timeout_seconds,
            )

            latency_ms = int((time.time() - start_time) * 1000)
            content = response.content[0].text if response.content else ""

            result = LLMResponse(
                content=content,
                model=settings.llm_model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                prompt_hash=prompt_hash,
                latency_ms=latency_ms,
                success=True,
            )

            logger.info(
                "LLM call succeeded",
                extra={"extra_data": {
                    "model": result.model,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "latency_ms": result.latency_ms,
                    "attempt": attempt + 1,
                }},
            )
            return result

        except Exception as exc:
            latency_ms = int((time.time() - start_time) * 1000)
            last_error = str(exc)
            logger.warning(
                "LLM call failed",
                extra={"extra_data": {
                    "attempt": attempt + 1,
                    "error": last_error,
                    "latency_ms": latency_ms,
                }},
            )

    # All retries exhausted
    raise LLMError(
        detail=f"LLM call failed after {1 + LLM_MAX_RETRIES} attempts: {last_error}"
    )
