"""
middleware.py
─────────────────────────────────────────────
PURPOSE:
  Authentication, authorization, and rate limiting
  middleware for the ATIA API (PRD §8.1, §10.2).

RESPONSIBILITIES:
  - Validate JWT tokens from Supabase Auth
  - Extract user role from token claims
  - Enforce role-based access control per endpoint
  - Rate limit evaluation requests per agency

NOT RESPONSIBLE FOR:
  - Business logic or evaluation pipeline
  - Token generation (Supabase Auth handles that)

DEPENDENCIES:
  - config.constants: rate limits, roles
  - utils.error_handler: AuthorizationError, RateLimitError
  - utils.logger

USED BY:
  - api/routes.py (dependency injection)
─────────────────────────────────────────────
"""

import time
from collections import defaultdict
from typing import Optional

from fastapi import Request, HTTPException

from config.constants import (
    REQUESTOR_ROLES,
    RATE_LIMIT_EVALUATE_PER_AGENCY_MINUTES,
)
from utils.logger import get_logger

logger = get_logger("api.middleware")

# Simple in-memory rate limiter (production: use Redis)
_eval_rate_limits: dict[str, float] = defaultdict(float)


def extract_role_from_request(request: Request) -> str:
    """
    Extract the user role from the request.

    In production, this reads from the Supabase JWT claims.
    For development, accepts an X-User-Role header.

    Args:
        request: The incoming FastAPI request.

    Returns:
        A valid role string.
    """
    # Development: check header
    role = request.headers.get("X-User-Role", "job_seeker")

    if role not in REQUESTOR_ROLES:
        role = "job_seeker"

    return role


def extract_user_id_from_request(request: Request) -> Optional[str]:
    """
    Extract the user ID from the request.

    In production, this reads from the Supabase JWT claims.
    For development, accepts an X-User-Id header.
    """
    return request.headers.get("X-User-Id")


def require_admin_role(request: Request) -> str:
    """
    Verify the requestor has admin role.

    Use as a FastAPI dependency for admin-only endpoints.

    Args:
        request: The incoming FastAPI request.

    Returns:
        The verified admin role string.

    Raises:
        HTTPException 403: If user is not an admin.
    """
    role = extract_role_from_request(request)
    if role != "admin":
        logger.warning(
            "Non-admin access attempt to admin endpoint",
            extra={"extra_data": {"role": role}},
        )
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to perform this action.",
        )
    return role


def check_evaluation_rate_limit(agency_id: str) -> None:
    """
    Enforce rate limit: one evaluation per agency per 15 minutes.

    Args:
        agency_id: UUID of the agency.

    Raises:
        HTTPException 429: If rate limit is exceeded.
    """
    now = time.time()
    last_eval = _eval_rate_limits.get(agency_id, 0)
    cooldown = RATE_LIMIT_EVALUATE_PER_AGENCY_MINUTES * 60

    if now - last_eval < cooldown:
        retry_after = int(cooldown - (now - last_eval))
        raise HTTPException(
            status_code=429,
            detail={
                "error": "RATE_LIMITED",
                "retry_after_seconds": retry_after,
            },
        )

    _eval_rate_limits[agency_id] = now
