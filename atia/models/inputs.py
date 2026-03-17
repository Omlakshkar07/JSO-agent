"""
inputs.py
─────────────────────────────────────────────
PURPOSE:
  Pydantic models for all data entering the ATIA agent.
  This includes the evaluation trigger request and the
  raw data retrieved from Supabase before processing.

RESPONSIBILITIES:
  - Define EvaluationTrigger (what starts an evaluation)
  - Define raw data shapes from Supabase queries
  - Define RawDataPackage (assembled query results)
  - Validate all inputs on construction

NOT RESPONSIBLE FOR:
  - Processed/weighted data (see internal.py)
  - Output schemas (see outputs.py)

DEPENDENCIES:
  - config.constants: enum values

USED BY:
  - api/routes.py (trigger construction)
  - data/agency_queries.py (raw data shapes)
  - agent/orchestrator.py (pipeline input)
─────────────────────────────────────────────
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from config.constants import TRIGGER_TYPES, REQUESTOR_ROLES


class EvaluationTrigger(BaseModel):
    """
    The input that starts an ATIA evaluation.

    Created when a user views an agency page, a new review
    is submitted, a placement updates, or the cron fires.
    """

    agency_id: str = Field(
        ...,
        description="UUID of the agency to evaluate.",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    trigger_type: str = Field(
        ...,
        description="What caused this evaluation.",
        examples=["ON_DEMAND"],
    )
    requestor_role: str = Field(
        default="job_seeker",
        description="Role of the user who triggered this evaluation.",
        examples=["job_seeker"],
    )
    requestor_id: Optional[str] = Field(
        default=None,
        description="UUID of the requesting user. Null for cron/events.",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.utcnow(),
        description="When the trigger was created.",
    )
    force_refresh: bool = Field(
        default=False,
        description="If true, bypass cache and force fresh evaluation.",
    )


class RawReview(BaseModel):
    """A single review from the reviews table."""

    id: str
    agency_id: str
    reviewer_id: str
    rating: float = Field(..., ge=1.0, le=5.0)
    review_text: Optional[str] = None
    created_at: datetime


class RawPlacement(BaseModel):
    """A single placement record from the placements table."""

    id: str
    agency_id: str
    candidate_id: Optional[str] = None
    outcome: str = Field(
        ...,
        description="'successful' or 'unsuccessful'.",
    )
    placement_source: str = Field(
        default="self_reported",
        description="'platform_tracked' or 'self_reported'.",
    )
    created_at: datetime


class RawFeedback(BaseModel):
    """A single feedback rating from the feedback_ratings table."""

    id: str
    agency_id: str
    score: float = Field(..., ge=1.0, le=5.0)
    created_at: datetime


class ReviewerMetadata(BaseModel):
    """Account age info for a reviewer (for CHECK-C)."""

    user_id: str
    account_age_days: int = Field(..., ge=0)


class AgencyMeta(BaseModel):
    """Agency metadata from the agencies table."""

    id: str
    name: str = ""
    registration_date: Optional[datetime] = None
    is_active: bool = True


class RawDataPackage(BaseModel):
    """
    The complete raw data package assembled from Supabase.

    This is the output of Step 2 (Data Retrieval) and the
    input to Steps 3–6 of the evaluation pipeline.
    """

    agency_id: str
    agency_meta: AgencyMeta
    reviews: list[RawReview] = Field(default_factory=list)
    placements: list[RawPlacement] = Field(default_factory=list)
    feedback_ratings: list[RawFeedback] = Field(default_factory=list)
    reviewer_metadata: list[ReviewerMetadata] = Field(default_factory=list)
    previous_profile: Optional[dict] = Field(
        default=None,
        description="Previous trust profile as dict, if one exists.",
    )
