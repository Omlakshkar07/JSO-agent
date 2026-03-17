"""
test_integrity_checks.py
─────────────────────────────────────────────
Tests for all 5 integrity checks in signal_auditor.py.
Each check is tested for:
  - Triggering condition (should flag)
  - Clean data (should NOT flag)
  - Edge case at boundary threshold
─────────────────────────────────────────────
"""

import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

# Add project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models.inputs import RawReview, RawPlacement, RawFeedback, ReviewerMetadata, AgencyMeta, RawDataPackage
from agent.signal_auditor import (
    check_a_review_velocity,
    check_b_rating_uniformity,
    check_c_reviewer_account_age,
    check_d_cross_signal_consistency,
    check_e_sentiment_mismatch,
    run_all_integrity_checks,
)


def _now():
    return datetime.now(timezone.utc)


def _make_review(*, days_ago=0, rating=4.0, reviewer_id="user1", review_text=None):
    """Helper to create a RawReview."""
    return RawReview(
        id=f"rev_{days_ago}_{reviewer_id}",
        agency_id="agency_test",
        reviewer_id=reviewer_id,
        rating=rating,
        review_text=review_text,
        created_at=_now() - timedelta(days=days_ago),
    )


def _make_data_package(
    reviews=None, placements=None, feedback=None, reviewer_meta=None,
):
    """Helper to build a RawDataPackage with test data."""
    return RawDataPackage(
        agency_id="agency_test",
        agency_meta=AgencyMeta(id="agency_test", name="Test Agency"),
        reviews=reviews or [],
        placements=placements or [],
        feedback_ratings=feedback or [],
        reviewer_metadata=reviewer_meta or [],
    )


# ─────────────────────────────────────────────
# CHECK-A: Review Velocity
# ─────────────────────────────────────────────

class TestCheckAReviewVelocity:
    """Tests for CHECK-A (review velocity anomaly)."""

    def test_velocity_spike_triggers_flag(self):
        """
        Agency with 5 reviews/day for 14d but only 0.5/day for 90d
        should be flagged (5 > 3 × 0.5 = 1.5 AND 5 > 2).
        """
        reviews = []
        # 70 reviews in last 14 days = 5/day
        for i in range(70):
            reviews.append(_make_review(days_ago=i % 14, reviewer_id=f"u{i}"))
        # 15 reviews scattered from day 30-90 = ~0.25/day baseline
        for i in range(15):
            reviews.append(_make_review(days_ago=30 + i * 4, reviewer_id=f"old{i}"))

        data = _make_data_package(reviews=reviews)
        result = check_a_review_velocity(data)

        assert result.triggered, f"Expected flag, got: {result.detail}"
        assert result.check_id == "CHECK-A"

    def test_normal_velocity_no_flag(self):
        """
        Agency with steady 1 review/day should NOT be flagged.
        """
        reviews = [_make_review(days_ago=i, reviewer_id=f"u{i}") for i in range(90)]
        data = _make_data_package(reviews=reviews)
        result = check_a_review_velocity(data)

        assert not result.triggered, f"Should not flag steady velocity: {result.detail}"

    def test_low_volume_no_flag(self):
        """
        Even if relative spike exists, < 2 reviews/day absolute → no flag.
        """
        reviews = [_make_review(days_ago=1, reviewer_id="u1")]
        data = _make_data_package(reviews=reviews)
        result = check_a_review_velocity(data)

        assert not result.triggered


# ─────────────────────────────────────────────
# CHECK-B: Rating Uniformity
# ─────────────────────────────────────────────

class TestCheckBRatingUniformity:
    """Tests for CHECK-B (rating uniformity anomaly)."""

    def test_all_identical_ratings_triggers_flag(self):
        """
        10+ ratings all equal to 5.0 in 30d → 100% uniformity → flag.
        """
        reviews = [_make_review(days_ago=i, rating=5.0, reviewer_id=f"u{i}") for i in range(15)]
        data = _make_data_package(reviews=reviews)
        result = check_b_rating_uniformity(data)

        assert result.triggered, f"Expected flag: {result.detail}"

    def test_mixed_ratings_no_flag(self):
        """
        Ratings of 3, 4, 5 mixed evenly → no uniformity → no flag.
        """
        reviews = []
        for i in range(15):
            rating = [3.0, 4.0, 5.0][i % 3]
            reviews.append(_make_review(days_ago=i, rating=rating, reviewer_id=f"u{i}"))

        data = _make_data_package(reviews=reviews)
        result = check_b_rating_uniformity(data)

        assert not result.triggered

    def test_below_minimum_count_no_flag(self):
        """
        Even 100% identical, if < 10 ratings → no flag.
        """
        reviews = [_make_review(days_ago=i, rating=5.0, reviewer_id=f"u{i}") for i in range(5)]
        data = _make_data_package(reviews=reviews)
        result = check_b_rating_uniformity(data)

        assert not result.triggered


# ─────────────────────────────────────────────
# CHECK-C: Reviewer Account Age
# ─────────────────────────────────────────────

class TestCheckCReviewerAccountAge:
    """Tests for CHECK-C (reviewer account age anomaly)."""

    def test_many_new_accounts_triggers_flag(self):
        """
        8+ reviews in 14d with 40%+ from accounts < 30 days → flag.
        """
        reviews = [
            _make_review(days_ago=i, reviewer_id=f"new{i}") for i in range(10)
        ]
        # 6 out of 10 are new accounts (60% > 40%)
        reviewer_meta = [
            ReviewerMetadata(user_id=f"new{i}", account_age_days=10) for i in range(6)
        ] + [
            ReviewerMetadata(user_id=f"new{i}", account_age_days=365) for i in range(6, 10)
        ]

        data = _make_data_package(reviews=reviews, reviewer_meta=reviewer_meta)
        result = check_c_reviewer_account_age(data)

        assert result.triggered, f"Expected flag: {result.detail}"

    def test_established_reviewers_no_flag(self):
        """
        All reviewers have old accounts → no flag.
        """
        reviews = [_make_review(days_ago=i, reviewer_id=f"u{i}") for i in range(10)]
        reviewer_meta = [
            ReviewerMetadata(user_id=f"u{i}", account_age_days=365) for i in range(10)
        ]

        data = _make_data_package(reviews=reviews, reviewer_meta=reviewer_meta)
        result = check_c_reviewer_account_age(data)

        assert not result.triggered

    def test_few_reviews_no_flag(self):
        """
        < 8 reviews in 14d → skip check even if all new accounts.
        """
        reviews = [_make_review(days_ago=i, reviewer_id=f"u{i}") for i in range(5)]
        reviewer_meta = [
            ReviewerMetadata(user_id=f"u{i}", account_age_days=1) for i in range(5)
        ]

        data = _make_data_package(reviews=reviews, reviewer_meta=reviewer_meta)
        result = check_c_reviewer_account_age(data)

        assert not result.triggered


# ─────────────────────────────────────────────
# CHECK-D: Cross-Signal Consistency
# ─────────────────────────────────────────────

class TestCheckDCrossSignal:
    """Tests for CHECK-D (cross-signal inconsistency)."""

    def test_high_sentiment_low_placement_triggers_flag(self):
        """
        Avg sentiment > 0.70 AND placement rate < 0.20 → flag.
        4.5 star avg → (4.5-1)/4 = 0.875 sentiment.
        """
        reviews = [_make_review(days_ago=i, rating=4.5, reviewer_id=f"u{i}") for i in range(20)]
        placements = [
            RawPlacement(id=f"p{i}", agency_id="agency_test", outcome="unsuccessful",
                        placement_source="self_reported", created_at=_now() - timedelta(days=i))
            for i in range(10)
        ] + [
            RawPlacement(id="p_good", agency_id="agency_test", outcome="successful",
                        placement_source="self_reported", created_at=_now())
        ]
        # 1 successful / 11 total = 9% rate < 20%

        data = _make_data_package(reviews=reviews, placements=placements)
        result = check_d_cross_signal_consistency(data)

        assert result.triggered, f"Expected flag: {result.detail}"

    def test_consistent_signals_no_flag(self):
        """
        Good reviews AND good placements → consistent → no flag.
        """
        reviews = [_make_review(days_ago=i, rating=4.5, reviewer_id=f"u{i}") for i in range(20)]
        placements = [
            RawPlacement(id=f"p{i}", agency_id="agency_test", outcome="successful",
                        placement_source="platform_tracked", created_at=_now() - timedelta(days=i))
            for i in range(10)
        ]

        data = _make_data_package(reviews=reviews, placements=placements)
        result = check_d_cross_signal_consistency(data)

        assert not result.triggered

    def test_no_placements_no_flag(self):
        """
        No placement data → can't do cross-signal check → no flag.
        """
        reviews = [_make_review(days_ago=i, rating=5.0, reviewer_id=f"u{i}") for i in range(20)]
        data = _make_data_package(reviews=reviews)
        result = check_d_cross_signal_consistency(data)

        assert not result.triggered


# ─────────────────────────────────────────────
# CHECK-E: Sentiment Mismatch (Mocked LLM)
# ─────────────────────────────────────────────

class TestCheckESentimentMismatch:
    """Tests for CHECK-E (sentiment-rating mismatch)."""

    @patch("agent.signal_auditor.call_llm")
    def test_high_mismatch_triggers_flag(self, mock_llm):
        """
        30%+ reviews where text sentiment contradicts star → flag.
        """
        # 10 reviews: 5-star rating but LLM says NEGATIVE sentiment
        reviews = [
            _make_review(days_ago=i, rating=5.0, reviewer_id=f"u{i}",
                        review_text=f"Terrible experience number {i}")
            for i in range(12)
        ]

        # Mock LLM to classify all as NEGATIVE
        mock_response = MagicMock()
        import json
        mock_response.content = json.dumps([
            {"review_id": f"rev_{i}_u{i}", "sentiment": "NEGATIVE"}
            for i in range(12)
        ])
        mock_llm.return_value = mock_response

        data = _make_data_package(reviews=reviews)
        result = check_e_sentiment_mismatch(data)

        assert result.triggered, f"Expected flag: {result.detail}"

    def test_too_few_text_reviews_no_flag(self):
        """
        < 10 reviews with text → skip LLM → no flag.
        """
        reviews = [
            _make_review(days_ago=i, rating=5.0, reviewer_id=f"u{i}",
                        review_text="Good" if i < 5 else None)
            for i in range(10)
        ]

        data = _make_data_package(reviews=reviews)
        result = check_e_sentiment_mismatch(data)

        assert not result.triggered

    @patch("agent.signal_auditor.call_llm")
    def test_matching_sentiments_no_flag(self, mock_llm):
        """
        High ratings with POSITIVE sentiment → consistent → no flag.
        """
        reviews = [
            _make_review(days_ago=i, rating=5.0, reviewer_id=f"u{i}",
                        review_text=f"Excellent service {i}")
            for i in range(12)
        ]

        mock_response = MagicMock()
        import json
        mock_response.content = json.dumps([
            {"review_id": f"rev_{i}_u{i}", "sentiment": "POSITIVE"}
            for i in range(12)
        ])
        mock_llm.return_value = mock_response

        data = _make_data_package(reviews=reviews)
        result = check_e_sentiment_mismatch(data)

        assert not result.triggered


# ─────────────────────────────────────────────
# Full Integrity Suite
# ─────────────────────────────────────────────

class TestFullIntegritySuite:
    """Integration test: running all checks together."""

    @patch("agent.signal_auditor.call_llm")
    def test_clean_agency_no_flags(self, mock_llm):
        """
        A well-behaved agency should trigger zero flags.
        """
        reviews = [
            _make_review(days_ago=i, rating=[3.0, 4.0, 5.0][i % 3],
                        reviewer_id=f"u{i}", review_text=f"Review {i}")
            for i in range(30)
        ]
        placements = [
            RawPlacement(id=f"p{i}", agency_id="agency_test", outcome="successful",
                        placement_source="platform_tracked", created_at=_now() - timedelta(days=i))
            for i in range(20)
        ]
        reviewer_meta = [
            ReviewerMetadata(user_id=f"u{i}", account_age_days=365) for i in range(30)
        ]

        # Mock LLM: all sentiments match ratings
        import json
        mock_response = MagicMock()
        mock_response.content = json.dumps([
            {"review_id": f"rev_{i}_u{i}", "sentiment": "POSITIVE" if [3.0, 4.0, 5.0][i % 3] >= 4 else "NEUTRAL"}
            for i in range(20)
        ])
        mock_llm.return_value = mock_response

        data = _make_data_package(
            reviews=reviews, placements=placements, reviewer_meta=reviewer_meta,
        )
        result = run_all_integrity_checks(data)

        assert not result.any_flag, f"Clean agency should have no flags, got: {[f.flag_id for f in result.flags]}"
        assert not result.any_p0_flag
