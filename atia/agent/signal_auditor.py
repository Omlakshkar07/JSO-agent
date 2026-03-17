"""
signal_auditor.py
─────────────────────────────────────────────
PURPOSE:
  Sub-Agent A — Signal Integrity Assessment.
  Runs all five manipulation detection checks on raw agency data
  BEFORE any scoring or weighting begins (PRD §6.2 Step 4).

RESPONSIBILITIES:
  - CHECK-A: Review velocity anomaly detection
  - CHECK-B: Rating uniformity anomaly detection
  - CHECK-C: Reviewer account age anomaly detection
  - CHECK-D: Cross-signal inconsistency detection
  - CHECK-E: Sentiment-rating mismatch detection (uses LLM)
  - Assemble IntegrityResult with all flags

NOT RESPONSIBLE FOR:
  - Data retrieval (already done in Step 2)
  - Signal weighting (see weighting_engine.py)
  - Trust profile synthesis (see trust_reasoner.py)

DEPENDENCIES:
  - config.constants: all check thresholds
  - models: inputs, outputs, internal
  - llm: prompts, client, parser (for CHECK-E only)
  - utils.logger

USED BY:
  - agent/orchestrator.py (Step 4)
─────────────────────────────────────────────
"""

from datetime import datetime, timezone, timedelta

from config.constants import (
    CHECK_A, CHECK_B, CHECK_C, CHECK_D, CHECK_E,
    CHECK_SEVERITIES, CHECK_LABELS,
    VELOCITY_MULTIPLIER, VELOCITY_ABSOLUTE_MINIMUM,
    VELOCITY_WINDOW_RECENT_DAYS, VELOCITY_WINDOW_BASELINE_DAYS,
    UNIFORMITY_THRESHOLD, UNIFORMITY_MIN_RATINGS, UNIFORMITY_WINDOW_DAYS,
    ACCOUNT_AGE_NEW_THRESHOLD_DAYS, ACCOUNT_AGE_PCT_THRESHOLD,
    ACCOUNT_AGE_MIN_REVIEWS, ACCOUNT_AGE_WINDOW_DAYS,
    CROSS_SIGNAL_SENTIMENT_THRESHOLD, CROSS_SIGNAL_PLACEMENT_THRESHOLD,
    SENTIMENT_MISMATCH_THRESHOLD, SENTIMENT_MISMATCH_MIN_SAMPLE,
    SENTIMENT_SAMPLE_SIZE, INTEGRITY_WEIGHT_REDUCTION_PCT,
)
from models.inputs import RawDataPackage
from models.outputs import IntegrityFlag
from models.internal import IntegrityCheckResult, IntegrityResult
from llm.prompts import build_sentiment_check_prompt
from llm.client import call_llm
from llm.parser import parse_sentiment_response
from utils.logger import get_logger

logger = get_logger("agent.signal_auditor")


def run_all_integrity_checks(data: RawDataPackage) -> IntegrityResult:
    """
    Run all five integrity checks on agency data (PRD §6.2 Step 4).

    Each check is independent — a failure in one does not block
    others. Results are assembled into a single IntegrityResult.

    Args:
        data: The raw data package from Step 2.

    Returns:
        IntegrityResult with all check results and any triggered flags.
    """
    checks = [
        check_a_review_velocity(data),
        check_b_rating_uniformity(data),
        check_c_reviewer_account_age(data),
        check_d_cross_signal_consistency(data),
        check_e_sentiment_mismatch(data),
    ]

    flags = _build_flags(checks)
    any_p0 = any(f.severity == "P0" for f in flags)
    any_flag = len(flags) > 0

    logger.info(
        "Integrity checks complete",
        extra={"extra_data": {
            "agency_id": data.agency_id,
            "checks_run": len(checks),
            "flags_triggered": [f.flag_id for f in flags],
            "any_p0": any_p0,
        }},
    )

    return IntegrityResult(
        checks=checks,
        flags=flags,
        any_p0_flag=any_p0,
        any_flag=any_flag,
    )


# ─── CHECK-A: Review Velocity ──────────────────────────────

def check_a_review_velocity(data: RawDataPackage) -> IntegrityCheckResult:
    """
    Detect review velocity anomalies (PRD §6.2 CHECK-A).

    Flags if: daily_avg_14d > (3× daily_avg_90d) AND daily_avg_14d > 2.
    """
    now = datetime.now(timezone.utc)
    cutoff_14d = now - timedelta(days=VELOCITY_WINDOW_RECENT_DAYS)
    cutoff_90d = now - timedelta(days=VELOCITY_WINDOW_BASELINE_DAYS)

    reviews_14d = [r for r in data.reviews if _to_utc(r.created_at) >= cutoff_14d]
    reviews_90d = [r for r in data.reviews if _to_utc(r.created_at) >= cutoff_90d]

    daily_avg_14d = len(reviews_14d) / VELOCITY_WINDOW_RECENT_DAYS
    daily_avg_90d = len(reviews_90d) / VELOCITY_WINDOW_BASELINE_DAYS if reviews_90d else 0

    threshold = max(daily_avg_90d * VELOCITY_MULTIPLIER, VELOCITY_ABSOLUTE_MINIMUM)
    triggered = daily_avg_14d > threshold and daily_avg_14d > VELOCITY_ABSOLUTE_MINIMUM

    return IntegrityCheckResult(
        check_id=CHECK_A,
        triggered=triggered,
        computed_value=round(daily_avg_14d, 2),
        threshold=round(threshold, 2),
        detail=(
            f"{len(reviews_14d)} reviews in 14d (avg {daily_avg_14d:.1f}/day) "
            f"vs 90d baseline of {daily_avg_90d:.1f}/day"
        ),
    )


# ─── CHECK-B: Rating Uniformity ────────────────────────────

def check_b_rating_uniformity(data: RawDataPackage) -> IntegrityCheckResult:
    """
    Detect rating uniformity anomalies (PRD §6.2 CHECK-B).

    Flags if: 95%+ of ratings in 30d have identical value AND >= 10 ratings.
    """
    now = datetime.now(timezone.utc)
    cutoff_30d = now - timedelta(days=UNIFORMITY_WINDOW_DAYS)
    recent_ratings = [r.rating for r in data.reviews if _to_utc(r.created_at) >= cutoff_30d]
    total = len(recent_ratings)

    if total < UNIFORMITY_MIN_RATINGS:
        return IntegrityCheckResult(
            check_id=CHECK_B, triggered=False,
            computed_value=0.0, threshold=UNIFORMITY_THRESHOLD,
            detail=f"Only {total} ratings in 30d (min {UNIFORMITY_MIN_RATINGS})",
        )

    from collections import Counter
    counts = Counter(recent_ratings)
    max_count = counts.most_common(1)[0][1]
    pct_identical = max_count / total

    return IntegrityCheckResult(
        check_id=CHECK_B,
        triggered=pct_identical >= UNIFORMITY_THRESHOLD,
        computed_value=round(pct_identical, 3),
        threshold=UNIFORMITY_THRESHOLD,
        detail=f"{max_count}/{total} ratings identical ({pct_identical:.0%})",
    )


# ─── CHECK-C: Reviewer Account Age ─────────────────────────

def check_c_reviewer_account_age(data: RawDataPackage) -> IntegrityCheckResult:
    """
    Detect reviewer account age anomalies (PRD §6.2 CHECK-C).

    Flags if: 40%+ of reviews in 14d are from accounts < 30 days old.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=ACCOUNT_AGE_WINDOW_DAYS)
    recent_reviews = [r for r in data.reviews if _to_utc(r.created_at) >= cutoff]
    total = len(recent_reviews)

    if total < ACCOUNT_AGE_MIN_REVIEWS:
        return IntegrityCheckResult(
            check_id=CHECK_C, triggered=False,
            computed_value=0.0, threshold=ACCOUNT_AGE_PCT_THRESHOLD,
            detail=f"Only {total} reviews in 14d (min {ACCOUNT_AGE_MIN_REVIEWS})",
        )

    # Build a lookup of account ages
    age_map = {rm.user_id: rm.account_age_days for rm in data.reviewer_metadata}
    new_accounts = sum(
        1 for r in recent_reviews
        if age_map.get(r.reviewer_id, 999) < ACCOUNT_AGE_NEW_THRESHOLD_DAYS
    )
    pct_new = new_accounts / total

    return IntegrityCheckResult(
        check_id=CHECK_C,
        triggered=pct_new >= ACCOUNT_AGE_PCT_THRESHOLD,
        computed_value=round(pct_new, 3),
        threshold=ACCOUNT_AGE_PCT_THRESHOLD,
        detail=f"{new_accounts}/{total} reviewers < {ACCOUNT_AGE_NEW_THRESHOLD_DAYS}d old ({pct_new:.0%})",
    )


# ─── CHECK-D: Cross-Signal Consistency ─────────────────────

def check_d_cross_signal_consistency(data: RawDataPackage) -> IntegrityCheckResult:
    """
    Detect cross-signal inconsistency (PRD §6.2 CHECK-D).

    Flags if: avg sentiment > 0.70 AND placement rate < 0.20.
    Sentiment is approximated from star ratings (normalized to 0-1).
    """
    if not data.reviews:
        return IntegrityCheckResult(
            check_id=CHECK_D, triggered=False,
            detail="No reviews available for cross-signal check",
        )

    # Approximate sentiment from star ratings (1-5 → 0-1 scale)
    avg_rating = sum(r.rating for r in data.reviews) / len(data.reviews)
    avg_sentiment = (avg_rating - 1) / 4  # normalize to 0-1

    # Calculate placement rate
    total_placements = len(data.placements)
    if total_placements == 0:
        return IntegrityCheckResult(
            check_id=CHECK_D, triggered=False,
            computed_value=round(avg_sentiment, 3),
            detail="No placement data for cross-signal check",
        )

    successful = sum(1 for p in data.placements if p.outcome == "successful")
    placement_rate = successful / total_placements

    triggered = (
        avg_sentiment > CROSS_SIGNAL_SENTIMENT_THRESHOLD
        and placement_rate < CROSS_SIGNAL_PLACEMENT_THRESHOLD
    )

    return IntegrityCheckResult(
        check_id=CHECK_D,
        triggered=triggered,
        computed_value=round(avg_sentiment, 3),
        threshold=CROSS_SIGNAL_SENTIMENT_THRESHOLD,
        detail=(
            f"Avg sentiment {avg_sentiment:.2f} vs placement rate "
            f"{placement_rate:.1%} ({successful}/{total_placements})"
        ),
    )


# ─── CHECK-E: Sentiment-Rating Mismatch (LLM) ──────────────

def check_e_sentiment_mismatch(data: RawDataPackage) -> IntegrityCheckResult:
    """
    Detect sentiment-rating mismatches using LLM (PRD §6.2 CHECK-E).

    Samples last 20 reviews with text. Flags if 30%+ have
    LLM-assessed sentiment disagreeing with star polarity.
    """
    # Get reviews with written text
    reviews_with_text = [
        r for r in data.reviews if r.review_text and r.review_text.strip()
    ][:SENTIMENT_SAMPLE_SIZE]

    if len(reviews_with_text) < SENTIMENT_MISMATCH_MIN_SAMPLE:
        return IntegrityCheckResult(
            check_id=CHECK_E, triggered=False,
            detail=f"Only {len(reviews_with_text)} reviews with text (min {SENTIMENT_MISMATCH_MIN_SAMPLE})",
        )

    try:
        sentiments = _get_llm_sentiments(reviews_with_text)
    except Exception as exc:
        logger.warning(f"CHECK-E LLM call failed: {exc}")
        return IntegrityCheckResult(
            check_id=CHECK_E, triggered=False,
            detail=f"LLM sentiment check failed: {exc}",
        )

    mismatches = _count_mismatches(reviews_with_text, sentiments)
    mismatch_pct = mismatches / len(reviews_with_text)

    return IntegrityCheckResult(
        check_id=CHECK_E,
        triggered=mismatch_pct >= SENTIMENT_MISMATCH_THRESHOLD,
        computed_value=round(mismatch_pct, 3),
        threshold=SENTIMENT_MISMATCH_THRESHOLD,
        detail=f"{mismatches}/{len(reviews_with_text)} reviews have sentiment-rating mismatch ({mismatch_pct:.0%})",
    )


def _get_llm_sentiments(reviews: list) -> dict[str, str]:
    """Call LLM to classify review text sentiments."""
    # PII safety: strip reviewer IDs, send only review_id + text
    reviews_for_llm = [
        {"review_id": r.id, "review_text": r.review_text}
        for r in reviews
    ]
    system_prompt, user_prompt = build_sentiment_check_prompt(reviews_for_llm)
    response = call_llm(system_prompt, user_prompt)
    parsed = parse_sentiment_response(response.content)
    return {item["review_id"]: item["sentiment"] for item in parsed}


def _count_mismatches(reviews: list, sentiments: dict[str, str]) -> int:
    """Count reviews where LLM sentiment disagrees with star polarity."""
    mismatches = 0
    for review in reviews:
        llm_sentiment = sentiments.get(review.id)
        if not llm_sentiment:
            continue
        star_polarity = _star_to_polarity(review.rating)
        if star_polarity != llm_sentiment:
            mismatches += 1
    return mismatches


def _star_to_polarity(rating: float) -> str:
    """Convert star rating to sentiment polarity for comparison."""
    if rating >= 4.0:
        return "POSITIVE"
    elif rating <= 2.0:
        return "NEGATIVE"
    return "NEUTRAL"


def _build_flags(checks: list[IntegrityCheckResult]) -> list[IntegrityFlag]:
    """Convert triggered checks into IntegrityFlag objects."""
    flags = []
    for check in checks:
        if check.triggered:
            flags.append(IntegrityFlag(
                flag_id=check.check_id,
                severity=CHECK_SEVERITIES[check.check_id],
                label=CHECK_LABELS[check.check_id],
                description=_flag_description(check.check_id),
                evidence_summary=check.detail,
                weight_reduction_pct=INTEGRITY_WEIGHT_REDUCTION_PCT,
            ))
    return flags


def _flag_description(check_id: str) -> str:
    """Plain-language description for each flag type."""
    descriptions = {
        CHECK_A: "An unusual spike in review submissions was detected.",
        CHECK_B: "An abnormally uniform pattern in ratings was detected.",
        CHECK_C: "A high proportion of reviews from recently created accounts was detected.",
        CHECK_D: "Positive review sentiment does not align with placement outcomes.",
        CHECK_E: "Written review text contradicts the star ratings given.",
    }
    return descriptions.get(check_id, "An integrity anomaly was detected.")


def _to_utc(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware in UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
