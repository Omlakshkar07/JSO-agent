"""
internal.py
─────────────────────────────────────────────
PURPOSE:
  Pydantic models for intermediate data that flows between
  agent modules during an evaluation. These are never
  exposed to the API — they exist only inside the pipeline.

RESPONSIBILITIES:
  - Define SufficiencyResult (Step 3 output)
  - Define IntegrityCheckResult / IntegrityResult (Step 4 output)
  - Define WeightedSignal / WeightedSignalSet (Step 5 output)
  - Define RawProfileDraft (Step 6 LLM output before validation)

NOT RESPONSIBLE FOR:
  - External-facing schemas (see outputs.py)
  - Raw data shapes (see inputs.py)

DEPENDENCIES:
  - models.outputs: IntegrityFlag

USED BY:
  - agent/signal_auditor.py (produces IntegrityResult)
  - agent/weighting_engine.py (produces WeightedSignalSet)
  - agent/trust_reasoner.py (consumes WeightedSignalSet)
  - agent/orchestrator.py (passes data between steps)
─────────────────────────────────────────────
"""

from typing import Optional

from pydantic import BaseModel, Field

from models.outputs import IntegrityFlag


class SufficiencyResult(BaseModel):
    """
    Output of Step 3 — Data Sufficiency Check.

    Determines whether enough data exists to run a
    meaningful evaluation, and caps the maximum
    confidence level based on data volume.
    """

    is_sufficient: bool = Field(
        ...,
        description="True if agency has enough data for evaluation.",
    )
    max_confidence: str = Field(
        ...,
        description="Ceiling on confidence: High, Medium, Low, or N/A.",
    )
    review_count: int = 0
    placement_count: int = 0


class IntegrityCheckResult(BaseModel):
    """Result of a single integrity check (one of five)."""

    check_id: str = Field(
        ...,
        description="CHECK-A through CHECK-E.",
    )
    triggered: bool = False
    computed_value: Optional[float] = Field(
        default=None,
        description="The computed metric value (e.g., pct_identical).",
    )
    threshold: Optional[float] = Field(
        default=None,
        description="The threshold that was compared against.",
    )
    detail: str = Field(
        default="",
        description="Human-readable explanation of the computation.",
    )


class IntegrityResult(BaseModel):
    """
    Combined output of all five integrity checks (Step 4).
    """

    checks: list[IntegrityCheckResult] = Field(default_factory=list)
    flags: list[IntegrityFlag] = Field(default_factory=list)
    any_p0_flag: bool = False
    any_flag: bool = False


class WeightedSignal(BaseModel):
    """A single signal with its computed weight and annotation."""

    signal_name: str = Field(
        ...,
        description="'reviews', 'placements', or 'ratings'.",
    )
    base_weight: float
    adjusted_weight: float
    final_weight: float = Field(
        ...,
        description="Weight after normalization (all signals sum to 1.0).",
    )
    integrity_annotation: str = Field(
        default="clean",
        description="'clean' or description of integrity issue.",
    )
    adjustments_applied: list[str] = Field(
        default_factory=list,
        description="List of adjustments applied to this signal.",
    )


class WeightedSignalSet(BaseModel):
    """
    Output of Step 5 — Signal Weighting.

    Contains the final normalized weights for all three
    signals, ready to be sent to the LLM for synthesis.
    """

    signals: list[WeightedSignal] = Field(default_factory=list)

    # Aggregate stats passed to LLM for context
    avg_star_rating: Optional[float] = None
    avg_star_rating_30d: Optional[float] = None
    placement_rate: Optional[float] = None
    placement_source: str = "self_reported"
    avg_feedback_score: Optional[float] = None
    recent_review_ratio: float = Field(
        default=0.0,
        description="Fraction of reviews from last 30 days.",
    )


class RawProfileDraft(BaseModel):
    """
    Raw LLM output from Sub-Agent B (Step 6) before validation.

    This is parsed defensively from the LLM JSON response.
    Fields may be missing or invalid — validation in Step 7
    catches and corrects issues.
    """

    trust_tier: str = ""
    confidence_level: str = ""
    key_strengths: list[str] = Field(default_factory=list)
    key_concerns: list[str] = Field(default_factory=list)
    explanation: str = ""
    audience_summaries: dict = Field(default_factory=dict)
    tier_change_note: Optional[str] = None


class EvaluationLog(BaseModel):
    """
    Structured log entry for each evaluation (PRD §12.2).

    Written to structured logging output after every evaluation.
    """

    agency_id: str
    evaluation_id: str = ""
    trigger_type: str = ""
    duration_ms: int = 0
    cache_hit: bool = False
    data_sufficiency_result: Optional[dict] = None
    integrity_checks: Optional[dict] = None
    flags_triggered: list[str] = Field(default_factory=list)
    final_tier: str = ""
    confidence_level: str = ""
    llm_call_count: int = 0
    llm_total_tokens_used: int = 0
    error: Optional[dict] = None
