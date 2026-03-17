"""
outputs.py
─────────────────────────────────────────────
PURPOSE:
  Pydantic models for all data leaving the ATIA agent.
  These match the database schemas defined in PRD §7.

RESPONSIBILITIES:
  - Define TrustProfile (primary output, PRD §7.1)
  - Define IntegrityFlag sub-schema (PRD §7.2)
  - Define SignalSummary sub-schema (PRD §7.4)
  - Define AudienceSummaries sub-schema
  - Define AuditLogEntry (PRD §7.3)
  - Define API response models

NOT RESPONSIBLE FOR:
  - Internal intermediate data (see internal.py)
  - Input validation (see inputs.py)

DEPENDENCIES:
  - config.constants: enum values

USED BY:
  - agent/trust_reasoner.py (produces TrustProfile)
  - agent/orchestrator.py (stores TrustProfile + AuditLogEntry)
  - api/routes.py (API response formatting)
─────────────────────────────────────────────
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class IntegrityFlag(BaseModel):
    """
    A detected manipulation pattern (PRD §7.2).

    Each flag records what check found the anomaly,
    how severe it is, and the specific evidence.
    """

    flag_id: str = Field(
        ...,
        description="CHECK-A through CHECK-E.",
        examples=["CHECK-A"],
    )
    severity: str = Field(
        ...,
        description="P0 (forces UnderReview) or P1 (reduces confidence).",
        examples=["P0"],
    )
    label: str = Field(
        ...,
        description="Human-readable flag name.",
        examples=["Review Velocity Anomaly"],
    )
    description: str = Field(
        ...,
        description="Plain-language explanation of what was found.",
    )
    evidence_summary: str = Field(
        ...,
        description="Specific metrics that triggered the flag.",
    )
    detected_at: datetime = Field(
        default_factory=lambda: datetime.utcnow(),
    )
    weight_reduction_pct: int = Field(
        default=40,
        description="Percentage by which signal weight was reduced.",
    )


class SignalSummary(BaseModel):
    """
    Aggregated signal statistics for a trust profile (PRD §7.4).
    """

    total_review_count: int = 0
    reviews_last_30d: int = 0
    reviews_last_90d: int = 0
    avg_star_rating_all_time: Optional[float] = None
    avg_star_rating_30d: Optional[float] = None
    total_placements: int = 0
    successful_placements: int = 0
    placement_rate: Optional[float] = None
    placement_source: str = "self_reported"
    avg_feedback_score: Optional[float] = None
    agency_tenure_days: int = 0
    anomalies_detected: bool = False
    anomaly_count: int = 0


class AudienceSummaries(BaseModel):
    """
    Four audience-specific summary strings (PRD §6.5).
    """

    job_seeker: str = Field(
        ...,
        description="40-80 words. Plain English. Empathetic. Actionable.",
    )
    hr_consultant: str = Field(
        ...,
        description="60-100 words. Professional. Constructive. Benchmarked.",
    )
    admin: str = Field(
        ...,
        description="100-200 words. Technical. Complete. Unfiltered.",
    )
    licensing: str = Field(
        ...,
        description="60-100 words. Formal. Structured. Decision-ready.",
    )


class TrustProfile(BaseModel):
    """
    The primary output of ATIA (PRD §7.1).

    One active profile exists per agency. Upserted on agency_id.
    """

    id: Optional[str] = None
    agency_id: str
    trust_tier: str = Field(
        ...,
        description="One of: High, Medium, Low, UnderReview, InsufficientData.",
    )
    confidence_level: str = Field(
        ...,
        description="One of: High, Medium, Low, N/A.",
    )
    key_strengths: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Top 3 evidence-backed strengths.",
    )
    key_concerns: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Top 3 evidence-backed concerns.",
    )
    integrity_flags: list[IntegrityFlag] = Field(default_factory=list)
    signal_summary: SignalSummary = Field(default_factory=SignalSummary)
    explanation: str = Field(
        ...,
        description="Plain-language reasoning, 50-150 words.",
    )
    audience_summaries: AudienceSummaries
    previous_tier: Optional[str] = None
    tier_change_note: Optional[str] = None
    evaluated_at: datetime = Field(
        default_factory=lambda: datetime.utcnow(),
    )
    evaluation_trigger: str = "ON_DEMAND"
    data_window_start: Optional[datetime] = None
    llm_model_version: str = ""
    created_at: datetime = Field(
        default_factory=lambda: datetime.utcnow(),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.utcnow(),
    )


class AuditLogEntry(BaseModel):
    """
    Immutable evaluation audit record (PRD §7.3).

    Append-only. No UPDATE, no DELETE permitted.
    """

    id: Optional[str] = None
    agency_id: str
    trust_profile_id: Optional[str] = None
    evaluation_trigger: str
    triggered_by: Optional[str] = None
    raw_signal_snapshot: dict = Field(default_factory=dict)
    integrity_checks_log: dict = Field(default_factory=dict)
    weighted_signals: dict = Field(default_factory=dict)
    llm_prompt_hash: str = ""
    llm_response_raw: str = ""
    final_trust_tier: str = ""
    final_confidence: str = ""
    override_applied: bool = False
    override_by: Optional[str] = None
    override_reason: Optional[str] = None
    override_tier: Optional[str] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.utcnow(),
    )


class TrustProfileResponse(BaseModel):
    """API response for GET /trust-profile/:agencyId (PRD §8.2)."""

    agency_id: str
    trust_tier: str
    confidence_level: str
    key_strengths: list[str]
    key_concerns: list[str]
    integrity_flags: list[IntegrityFlag]
    summary: str  # audience-appropriate summary
    tier_change_note: Optional[str] = None
    evaluated_at: datetime
    data_is_stale: bool = False


class EvaluationAcceptedResponse(BaseModel):
    """API response for POST /evaluate/:agencyId (PRD §8.2)."""

    job_id: str
    estimated_completion_seconds: int = 8


class OverrideRequest(BaseModel):
    """Request body for POST /override/:agencyId (PRD §8.2)."""

    override_tier: str = Field(
        ...,
        description="Target tier: High, Medium, Low, or UnderReview.",
    )
    reason: str = Field(
        ...,
        min_length=20,
        description="Mandatory reason. Minimum 20 characters.",
    )


class AnomalyQueueItem(BaseModel):
    """Single item in the anomaly queue response."""

    agency_id: str
    agency_name: str
    flags: list[IntegrityFlag]
    flagged_since: datetime
    trust_tier: str
