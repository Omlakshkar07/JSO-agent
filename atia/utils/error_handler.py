"""
error_handler.py
─────────────────────────────────────────────
PURPOSE:
  Custom exception hierarchy for the ATIA agent.
  Every error has an error code, user-safe message,
  and developer-facing detail. Raw Python errors
  never reach the user.

RESPONSIBILITIES:
  - Define all custom exceptions
  - Provide error normalization for API responses
  - Map internal errors to HTTP status codes

NOT RESPONSIBLE FOR:
  - Logging errors (caller logs before raising)
  - Retry logic (see llm/client.py)

DEPENDENCIES:
  - None

USED BY:
  - Every module that can fail
  - api/routes.py (error → HTTP response mapping)
─────────────────────────────────────────────
"""

from typing import Any


class ATIAError(Exception):
    """
    Base exception for all ATIA agent errors.

    Every ATIA error carries a machine-readable code,
    a user-safe message, and a developer detail string.
    """

    def __init__(
        self,
        code: str,
        user_message: str,
        detail: str = "",
        status_code: int = 500,
    ) -> None:
        self.code = code
        self.user_message = user_message
        self.detail = detail or user_message
        self.status_code = status_code
        super().__init__(self.detail)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict safe for API responses."""
        return {
            "error": self.code,
            "message": self.user_message,
            "status_code": self.status_code,
        }


class DataRetrievalError(ATIAError):
    """Raised when Supabase queries fail or time out."""

    def __init__(self, detail: str = "Database query failed") -> None:
        super().__init__(
            code="DATA_RETRIEVAL_FAILED",
            user_message="Unable to retrieve agency data. Please try again.",
            detail=detail,
            status_code=503,
        )


class InsufficientDataError(ATIAError):
    """Raised when an agency has too little data for evaluation."""

    def __init__(self, agency_id: str = "") -> None:
        super().__init__(
            code="INSUFFICIENT_DATA",
            user_message="This agency does not have enough data for a trust assessment yet.",
            detail=f"Agency {agency_id} below data sufficiency thresholds",
            status_code=200,  # not an error from the user's perspective
        )


class LLMError(ATIAError):
    """Raised when the Anthropic API call fails."""

    def __init__(self, detail: str = "LLM call failed") -> None:
        super().__init__(
            code="LLM_ERROR",
            user_message="Trust evaluation is temporarily unavailable.",
            detail=detail,
            status_code=503,
        )


class LLMParseError(ATIAError):
    """Raised when LLM output cannot be parsed into valid JSON."""

    def __init__(self, detail: str = "LLM returned malformed output") -> None:
        super().__init__(
            code="LLM_PARSE_ERROR",
            user_message="Trust evaluation encountered a processing error.",
            detail=detail,
            status_code=503,
        )


class ValidationError(ATIAError):
    """Raised when a trust profile fails post-LLM validation."""

    def __init__(self, detail: str = "Validation failed") -> None:
        super().__init__(
            code="VALIDATION_ERROR",
            user_message="Trust evaluation encountered a validation error.",
            detail=detail,
            status_code=500,
        )


class RateLimitError(ATIAError):
    """Raised when an evaluation request exceeds the rate limit."""

    def __init__(self, retry_after_seconds: int = 900) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            code="RATE_LIMITED",
            user_message="Too many evaluation requests. Please try again later.",
            detail=f"Rate limited. Retry after {retry_after_seconds}s",
            status_code=429,
        )

    def to_dict(self) -> dict[str, Any]:
        """Include retry_after in the response."""
        base = super().to_dict()
        base["retry_after_seconds"] = self.retry_after_seconds
        return base


class AuthorizationError(ATIAError):
    """Raised when a user lacks permission for an action."""

    def __init__(self, detail: str = "Unauthorized") -> None:
        super().__init__(
            code="FORBIDDEN",
            user_message="You do not have permission to perform this action.",
            detail=detail,
            status_code=403,
        )


class OverrideValidationError(ATIAError):
    """Raised when an admin override request is invalid."""

    def __init__(self, detail: str = "Invalid override request") -> None:
        super().__init__(
            code="INVALID_OVERRIDE",
            user_message=detail,
            detail=detail,
            status_code=400,
        )


def normalize_error(error: Exception) -> dict[str, Any]:
    """
    Convert any exception to a consistent API error response.

    ATIA errors are serialized directly. Unknown errors become
    a generic 500 response — raw error details are never exposed.

    Args:
        error: Any exception caught in the API layer.

    Returns:
        A dict with 'error', 'message', and 'status_code' keys.
    """
    if isinstance(error, ATIAError):
        return error.to_dict()

    # Never expose internal error details to the user
    return {
        "error": "INTERNAL_ERROR",
        "message": "An unexpected error occurred. Please try again.",
        "status_code": 500,
    }
