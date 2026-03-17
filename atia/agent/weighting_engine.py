"""
weighting_engine.py
─────────────────────────────────────────────
PURPOSE:
  Compute weighted signal values for trust profile synthesis.
  Implements the weight adjustment rules from PRD §6.2 Step 5.

RESPONSIBILITIES:
  - Apply base weights (reviews=0.40, placements=0.40, ratings=0.20)
  - Apply sequential adjustments: recency, volume, integrity, verification
  - Normalize all weights to sum to 1.0
  - Compute aggregate statistics for the LLM

NOT RESPONSIBLE FOR:
  - Data retrieval (see agency_queries.py)
  - Integrity checks (see signal_auditor.py)
  - Trust synthesis (see trust_reasoner.py)

DEPENDENCIES:
  - config.constants: base weights, adjustment factors
  - models: inputs, internal, outputs
  - utils.logger

USED BY:
  - agent/orchestrator.py (Step 5)
─────────────────────────────────────────────
"""

from datetime import datetime, timezone, timedelta

from config.constants import (
    BASE_WEIGHT_REVIEWS, BASE_WEIGHT_PLACEMENTS, BASE_WEIGHT_RATINGS,
    RECENCY_BOOST_MULTIPLIER, RECENCY_WINDOW_DAYS,
    VOLUME_DISCOUNT_THRESHOLD, VOLUME_DISCOUNT_REDUCTION,
    INTEGRITY_PENALTY_REDUCTION,
    VERIFICATION_BONUS, SELF_REPORT_PENALTY,
    PLACEMENT_SOURCE_TRACKED, PLACEMENT_SOURCE_SELF_REPORTED,
)
from models.inputs import RawDataPackage
from models.internal import (
    IntegrityResult,
    WeightedSignal,
    WeightedSignalSet,
)
from utils.logger import get_logger

logger = get_logger("agent.weighting_engine")


def compute_weighted_signals(
    data: RawDataPackage,
    integrity: IntegrityResult,
) -> WeightedSignalSet:
    """
    Compute weighted signals for trust synthesis (PRD §6.2 Step 5).

    Applies adjustments in sequence: recency → volume → integrity
    → verification/self-report. Then normalizes to sum to 1.0.

    Args:
        data: The raw data package from Step 2.
        integrity: The integrity check results from Step 4.

    Returns:
        WeightedSignalSet with final normalized weights and aggregate stats.
    """
    # Build flag lookup: which signals have integrity issues
    flagged_signals = _get_flagged_signal_names(integrity)

    review_signal = _build_review_signal(data, flagged_signals)
    placement_signal = _build_placement_signal(data, flagged_signals)
    rating_signal = _build_rating_signal(data, flagged_signals)

    signals = [review_signal, placement_signal, rating_signal]
    signals = _normalize_weights(signals)

    # Compute aggregate stats for the LLM
    stats = _compute_aggregate_stats(data)

    return WeightedSignalSet(
        signals=signals,
        avg_star_rating=stats["avg_star_rating"],
        avg_star_rating_30d=stats["avg_star_rating_30d"],
        placement_rate=stats["placement_rate"],
        placement_source=stats["placement_source"],
        avg_feedback_score=stats["avg_feedback_score"],
        recent_review_ratio=stats["recent_review_ratio"],
    )


def _build_review_signal(
    data: RawDataPackage,
    flagged: set[str],
) -> WeightedSignal:
    """Build the review signal with adjustments."""
    weight = BASE_WEIGHT_REVIEWS
    adjustments = []

    # Recency boost: reviews in last 30d weighted 1.5×
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RECENCY_WINDOW_DAYS)
    recent = sum(1 for r in data.reviews if _to_utc(r.created_at) >= cutoff)
    total = len(data.reviews)
    if total > 0 and recent / total > 0.3:
        weight *= RECENCY_BOOST_MULTIPLIER
        adjustments.append(f"recency_boost: ×{RECENCY_BOOST_MULTIPLIER}")

    # Volume discount: if review_count < 25, reduce by 20%
    if total < VOLUME_DISCOUNT_THRESHOLD:
        weight *= (1 - VOLUME_DISCOUNT_REDUCTION)
        adjustments.append(f"volume_discount: -{VOLUME_DISCOUNT_REDUCTION:.0%}")

    base = BASE_WEIGHT_REVIEWS
    adjusted = weight

    # Integrity penalty
    if "reviews" in flagged:
        weight *= (1 - INTEGRITY_PENALTY_REDUCTION)
        adjustments.append(f"integrity_penalty: -{INTEGRITY_PENALTY_REDUCTION:.0%}")

    return WeightedSignal(
        signal_name="reviews",
        base_weight=base,
        adjusted_weight=adjusted,
        final_weight=weight,
        integrity_annotation="flagged" if "reviews" in flagged else "clean",
        adjustments_applied=adjustments,
    )


def _build_placement_signal(
    data: RawDataPackage,
    flagged: set[str],
) -> WeightedSignal:
    """Build the placement signal with adjustments."""
    weight = BASE_WEIGHT_PLACEMENTS
    adjustments = []

    # Determine predominant placement source
    source = _predominant_placement_source(data)

    # Verification bonus / self-report penalty
    if source == PLACEMENT_SOURCE_TRACKED:
        weight *= (1 + VERIFICATION_BONUS)
        adjustments.append(f"verification_bonus: +{VERIFICATION_BONUS:.0%}")
    elif source == PLACEMENT_SOURCE_SELF_REPORTED:
        weight *= (1 - SELF_REPORT_PENALTY)
        adjustments.append(f"self_report_penalty: -{SELF_REPORT_PENALTY:.0%}")

    base = BASE_WEIGHT_PLACEMENTS
    adjusted = weight

    # Integrity penalty
    if "placements" in flagged:
        weight *= (1 - INTEGRITY_PENALTY_REDUCTION)
        adjustments.append(f"integrity_penalty: -{INTEGRITY_PENALTY_REDUCTION:.0%}")

    return WeightedSignal(
        signal_name="placements",
        base_weight=base,
        adjusted_weight=adjusted,
        final_weight=weight,
        integrity_annotation="flagged" if "placements" in flagged else "clean",
        adjustments_applied=adjustments,
    )


def _build_rating_signal(
    data: RawDataPackage,
    flagged: set[str],
) -> WeightedSignal:
    """Build the feedback rating signal with adjustments."""
    weight = BASE_WEIGHT_RATINGS
    adjustments = []
    base = BASE_WEIGHT_RATINGS
    adjusted = weight

    # Integrity penalty
    if "ratings" in flagged:
        weight *= (1 - INTEGRITY_PENALTY_REDUCTION)
        adjustments.append(f"integrity_penalty: -{INTEGRITY_PENALTY_REDUCTION:.0%}")

    return WeightedSignal(
        signal_name="ratings",
        base_weight=base,
        adjusted_weight=adjusted,
        final_weight=weight,
        integrity_annotation="flagged" if "ratings" in flagged else "clean",
        adjustments_applied=adjustments,
    )


def _normalize_weights(signals: list[WeightedSignal]) -> list[WeightedSignal]:
    """Normalize all signal weights to sum to 1.0."""
    total = sum(s.final_weight for s in signals)
    if total <= 0:
        # Fallback: equal weights
        for s in signals:
            s.final_weight = 1.0 / len(signals)
        return signals

    for s in signals:
        s.final_weight = round(s.final_weight / total, 4)

    return signals


def _get_flagged_signal_names(integrity: IntegrityResult) -> set[str]:
    """Map integrity flags to affected signal names."""
    flagged = set()
    for flag in integrity.flags:
        # CHECK-A, B, E affect reviews; CHECK-D affects both
        if flag.flag_id in ("CHECK-A", "CHECK-B", "CHECK-E"):
            flagged.add("reviews")
        if flag.flag_id == "CHECK-C":
            flagged.add("reviews")
        if flag.flag_id == "CHECK-D":
            flagged.add("reviews")
            flagged.add("placements")
    return flagged


def _predominant_placement_source(data: RawDataPackage) -> str:
    """Determine the most common placement data source."""
    if not data.placements:
        return PLACEMENT_SOURCE_SELF_REPORTED
    tracked = sum(1 for p in data.placements if p.placement_source == PLACEMENT_SOURCE_TRACKED)
    return PLACEMENT_SOURCE_TRACKED if tracked > len(data.placements) / 2 else PLACEMENT_SOURCE_SELF_REPORTED


def _compute_aggregate_stats(data: RawDataPackage) -> dict:
    """Compute aggregate statistics for the LLM context."""
    now = datetime.now(timezone.utc)
    cutoff_30d = now - timedelta(days=RECENCY_WINDOW_DAYS)

    all_ratings = [r.rating for r in data.reviews]
    recent_ratings = [r.rating for r in data.reviews if _to_utc(r.created_at) >= cutoff_30d]

    total_placements = len(data.placements)
    successful = sum(1 for p in data.placements if p.outcome == "successful")

    feedback_scores = [f.score for f in data.feedback_ratings]

    return {
        "avg_star_rating": round(sum(all_ratings) / len(all_ratings), 2) if all_ratings else None,
        "avg_star_rating_30d": round(sum(recent_ratings) / len(recent_ratings), 2) if recent_ratings else None,
        "placement_rate": round(successful / total_placements, 3) if total_placements > 0 else None,
        "placement_source": _predominant_placement_source(data),
        "avg_feedback_score": round(sum(feedback_scores) / len(feedback_scores), 2) if feedback_scores else None,
        "recent_review_ratio": round(len(recent_ratings) / len(all_ratings), 2) if all_ratings else 0.0,
    }


def _to_utc(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware in UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
