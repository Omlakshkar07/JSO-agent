"""
constants.py
─────────────────────────────────────────────
PURPOSE:
  Single source of truth for all magic numbers, thresholds,
  and string constants used throughout the ATIA agent.
  No other file in the codebase should contain hardcoded
  threshold values or enum-like strings.

RESPONSIBILITIES:
  - Define all integrity check thresholds (PRD §6.2 Step 4)
  - Define signal weighting base values (PRD §6.2 Step 5)
  - Define trust tier and confidence level enums
  - Define audience types and trigger types

NOT RESPONSIBLE FOR:
  - Runtime configuration (see settings.py)
  - Environment-specific values (see .env)

DEPENDENCIES:
  - None (this is the lowest-level module)

USED BY:
  - agent/signal_auditor.py (integrity thresholds)
  - agent/weighting_engine.py (base weights, adjustments)
  - utils/validators.py (tier/confidence enums)
  - models/*.py (enum values)
─────────────────────────────────────────────
"""

# ─── Trust Tier Values ──────────────────────────────────────
# PRD §5.3 FR-020: exactly five values, no others permitted
TRUST_TIERS = ("High", "Medium", "Low", "UnderReview", "InsufficientData")

# ─── Confidence Level Values ────────────────────────────────
# PRD §5.3 FR-023
CONFIDENCE_LEVELS = ("High", "Medium", "Low", "N/A")

# ─── Evaluation Trigger Types ──────────────────────────────
# PRD §6.2 Step 1
TRIGGER_TYPES = (
    "ON_DEMAND",
    "NEW_REVIEW",
    "PLACEMENT_UPD",
    "CRON_DAILY",
    "OVERRIDE_CHK",
)

# ─── User Roles ────────────────────────────────────────────
REQUESTOR_ROLES = ("job_seeker", "hr_consultant", "admin", "licensing")

# ─── Integrity Check IDs ───────────────────────────────────
# PRD §7.2: flag_id values
CHECK_A = "CHECK-A"  # Review velocity anomaly
CHECK_B = "CHECK-B"  # Rating uniformity anomaly
CHECK_C = "CHECK-C"  # Reviewer account age anomaly
CHECK_D = "CHECK-D"  # Cross-signal inconsistency
CHECK_E = "CHECK-E"  # Sentiment-rating mismatch

# ─── Integrity Check Severities ─────────────────────────────
# PRD §6.2: CHECK-A through CHECK-D are P0, CHECK-E is P1
SEVERITY_P0 = "P0"
SEVERITY_P1 = "P1"

CHECK_SEVERITIES = {
    CHECK_A: SEVERITY_P0,
    CHECK_B: SEVERITY_P0,
    CHECK_C: SEVERITY_P0,
    CHECK_D: SEVERITY_P0,
    CHECK_E: SEVERITY_P1,
}

# ─── Integrity Check Labels ────────────────────────────────
CHECK_LABELS = {
    CHECK_A: "Review Velocity Anomaly",
    CHECK_B: "Rating Uniformity Anomaly",
    CHECK_C: "Reviewer Account Age Anomaly",
    CHECK_D: "Cross-Signal Inconsistency",
    CHECK_E: "Sentiment-Rating Mismatch",
}

# ─── CHECK-A: Review Velocity Thresholds ───────────────────
# PRD §6.2 Step 4 CHECK-A:
#   Flag IF daily_avg_14d > (3 × daily_avg_90d) AND daily_avg_14d > 2
VELOCITY_MULTIPLIER = 3.0
VELOCITY_ABSOLUTE_MINIMUM = 2.0  # ignore micro-agencies
VELOCITY_WINDOW_RECENT_DAYS = 14
VELOCITY_WINDOW_BASELINE_DAYS = 90

# ─── CHECK-B: Rating Uniformity Thresholds ─────────────────
# PRD §6.2 Step 4 CHECK-B:
#   Flag IF pct_identical >= 0.95 AND total_ratings_30d >= 10
UNIFORMITY_THRESHOLD = 0.95
UNIFORMITY_MIN_RATINGS = 10
UNIFORMITY_WINDOW_DAYS = 30

# ─── CHECK-C: Reviewer Account Age Thresholds ──────────────
# PRD §6.2 Step 4 CHECK-C:
#   Flag IF pct_new >= 0.40 AND count(reviews_14d) >= 8
ACCOUNT_AGE_NEW_THRESHOLD_DAYS = 30  # accounts < 30 days = "new"
ACCOUNT_AGE_PCT_THRESHOLD = 0.40
ACCOUNT_AGE_MIN_REVIEWS = 8
ACCOUNT_AGE_WINDOW_DAYS = 14

# ─── CHECK-D: Cross-Signal Consistency Thresholds ──────────
# PRD §6.2 Step 4 CHECK-D:
#   Flag IF avg_sentiment_score > 0.70 AND placement_rate < 0.20
CROSS_SIGNAL_SENTIMENT_THRESHOLD = 0.70
CROSS_SIGNAL_PLACEMENT_THRESHOLD = 0.20

# ─── CHECK-E: Sentiment-Rating Mismatch Thresholds ─────────
# PRD §6.2 Step 4 CHECK-E:
#   Flag IF mismatch_pct >= 0.30 AND sample_size >= 10
SENTIMENT_MISMATCH_THRESHOLD = 0.30
SENTIMENT_MISMATCH_MIN_SAMPLE = 10
SENTIMENT_SAMPLE_SIZE = 20  # last 20 reviews with written text

# ─── Weight Reduction for Flagged Signals ───────────────────
# PRD §6.2 Step 4: "each active flag reduces its signal's weight by 40%"
INTEGRITY_WEIGHT_REDUCTION_PCT = 40

# ─── Data Sufficiency Thresholds ────────────────────────────
# PRD §6.2 Step 3
MIN_REVIEWS_FOR_EVALUATION = 10
MIN_PLACEMENTS_FOR_EVALUATION = 5

# Confidence ceiling based on review count (PRD §6.2 Step 3)
CONFIDENCE_HIGH_MIN_REVIEWS = 75
CONFIDENCE_MEDIUM_MIN_REVIEWS = 25
CONFIDENCE_LOW_MIN_REVIEWS = 10  # same as MIN_REVIEWS

# ─── Signal Base Weights ───────────────────────────────────
# PRD §6.2 Step 5: reviews=0.40, placements=0.40, ratings=0.20
BASE_WEIGHT_REVIEWS = 0.40
BASE_WEIGHT_PLACEMENTS = 0.40
BASE_WEIGHT_RATINGS = 0.20

# ─── Weight Adjustments ───────────────────────────────────
# PRD §6.2 Step 5
RECENCY_BOOST_MULTIPLIER = 1.5  # reviews in last 30d weighted 1.5×
RECENCY_WINDOW_DAYS = 30
VOLUME_DISCOUNT_THRESHOLD = 25  # if review_count < 25
VOLUME_DISCOUNT_REDUCTION = 0.20  # reduce review weight by 20%
INTEGRITY_PENALTY_REDUCTION = 0.40  # per active flag
VERIFICATION_BONUS = 0.25  # platform_tracked placement bonus
SELF_REPORT_PENALTY = 0.30  # self_reported placement penalty

# ─── Placement Source Values ───────────────────────────────
PLACEMENT_SOURCE_TRACKED = "platform_tracked"
PLACEMENT_SOURCE_SELF_REPORTED = "self_reported"

# ─── Trust Tier Deterministic Rules ─────────────────────────
# PRD §6.3: conditions for each tier
TIER_HIGH_MIN_PLACEMENT_RATE = 0.40
TIER_HIGH_MIN_FEEDBACK = 4.0
TIER_HIGH_MIN_REVIEWS = 75

TIER_MEDIUM_MIN_PLACEMENT_RATE = 0.20
TIER_MEDIUM_MIN_FEEDBACK = 3.5
TIER_MEDIUM_MIN_REVIEWS = 25

# ─── Cache / Staleness ─────────────────────────────────────
CACHE_TTL_HOURS = 24
STALE_CACHE_MAX_HOURS = 72  # serve stale cache up to 72h on error

# ─── API Rate Limits ───────────────────────────────────────
# PRD §8.1
RATE_LIMIT_GET_PER_MINUTE = 60
RATE_LIMIT_EVALUATE_PER_AGENCY_MINUTES = 15

# ─── LLM Constraints ───────────────────────────────────────
LLM_TIMEOUT_SECONDS = 30
LLM_MAX_RETRIES = 1  # retry once on failure

# ─── Explanation Constraints ────────────────────────────────
EXPLANATION_MIN_WORDS = 50
EXPLANATION_MAX_WORDS = 150

# ─── Override Constraints ──────────────────────────────────
OVERRIDE_REASON_MIN_LENGTH = 20

# ─── Cron ───────────────────────────────────────────────────
CRON_SCHEDULE_UTC_HOUR = 2  # 02:00 UTC per PRD §6.2 Step 1
CRON_MAX_DURATION_HOURS = 6  # alert if exceeds this

# ─── Licensing Threshold ───────────────────────────────────
# PRD Gap #4: not specified, defaulting to tier-based
LICENSING_PASS_TIERS = ("High", "Medium")
