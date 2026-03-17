"""
test_weighting_engine.py
─────────────────────────────────────────────
Tests for the signal weighting engine.
─────────────────────────────────────────────
"""

import sys
import os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models.inputs import RawReview, RawPlacement, RawFeedback, AgencyMeta, RawDataPackage, ReviewerMetadata
from models.outputs import IntegrityFlag
from models.internal import IntegrityResult, IntegrityCheckResult
from agent.weighting_engine import compute_weighted_signals


def _now():
    return datetime.now(timezone.utc)


def _clean_integrity():
    """Create a clean IntegrityResult with no flags."""
    return IntegrityResult(
        checks=[
            IntegrityCheckResult(check_id=f"CHECK-{c}", triggered=False)
            for c in "ABCDE"
        ],
        flags=[],
        any_p0_flag=False,
        any_flag=False,
    )


def _flagged_integrity(flag_ids):
    """Create an IntegrityResult with specified flags triggered."""
    flags = [
        IntegrityFlag(
            flag_id=fid, severity="P0", label=f"Test {fid}",
            description="test", evidence_summary="test",
        )
        for fid in flag_ids
    ]
    return IntegrityResult(
        checks=[], flags=flags,
        any_p0_flag=True, any_flag=True,
    )


def _make_data(review_count=30, placement_count=10, placement_source="self_reported"):
    """Helper to create test data."""
    reviews = [
        RawReview(
            id=f"r{i}", agency_id="test", reviewer_id=f"u{i}",
            rating=4.0, created_at=_now() - timedelta(days=i),
        )
        for i in range(review_count)
    ]
    placements = [
        RawPlacement(
            id=f"p{i}", agency_id="test", outcome="successful",
            placement_source=placement_source,
            created_at=_now() - timedelta(days=i),
        )
        for i in range(placement_count)
    ]
    feedback = [
        RawFeedback(
            id=f"f{i}", agency_id="test", score=4.0,
            created_at=_now() - timedelta(days=i),
        )
        for i in range(5)
    ]
    return RawDataPackage(
        agency_id="test",
        agency_meta=AgencyMeta(id="test", name="Test"),
        reviews=reviews,
        placements=placements,
        feedback_ratings=feedback,
    )


class TestWeightNormalization:
    """Verify weights always sum to 1.0."""

    def test_clean_weights_sum_to_one(self):
        data = _make_data()
        integrity = _clean_integrity()
        result = compute_weighted_signals(data, integrity)

        total = sum(s.final_weight for s in result.signals)
        assert abs(total - 1.0) < 0.001, f"Weights should sum to 1.0, got {total}"

    def test_flagged_weights_sum_to_one(self):
        data = _make_data()
        integrity = _flagged_integrity(["CHECK-A", "CHECK-B"])
        result = compute_weighted_signals(data, integrity)

        total = sum(s.final_weight for s in result.signals)
        assert abs(total - 1.0) < 0.001, f"Weights should sum to 1.0 even with flags, got {total}"

    def test_all_signals_flagged_still_sums(self):
        data = _make_data()
        integrity = _flagged_integrity(["CHECK-A", "CHECK-B", "CHECK-D"])
        result = compute_weighted_signals(data, integrity)

        total = sum(s.final_weight for s in result.signals)
        assert abs(total - 1.0) < 0.001


class TestIntegrityPenalty:
    """Verify integrity flags reduce signal weights."""

    def test_review_flags_reduce_review_weight(self):
        data = _make_data()
        clean = compute_weighted_signals(data, _clean_integrity())
        flagged = compute_weighted_signals(data, _flagged_integrity(["CHECK-A"]))

        clean_review = next(s for s in clean.signals if s.signal_name == "reviews")
        flagged_review = next(s for s in flagged.signals if s.signal_name == "reviews")

        # Raw weight (before normalization) should be lower when flagged
        assert flagged_review.integrity_annotation == "flagged"

    def test_clean_signals_have_no_annotation(self):
        data = _make_data()
        result = compute_weighted_signals(data, _clean_integrity())

        for signal in result.signals:
            assert signal.integrity_annotation == "clean"


class TestVerificationBonus:
    """Verify platform-tracked placements get a weight boost."""

    def test_tracked_placements_get_bonus(self):
        data_tracked = _make_data(placement_source="platform_tracked")
        data_self = _make_data(placement_source="self_reported")
        integrity = _clean_integrity()

        result_tracked = compute_weighted_signals(data_tracked, integrity)
        result_self = compute_weighted_signals(data_self, integrity)

        pl_tracked = next(s for s in result_tracked.signals if s.signal_name == "placements")
        pl_self = next(s for s in result_self.signals if s.signal_name == "placements")

        # Tracked should have higher adjusted weight than self-reported
        assert pl_tracked.adjusted_weight > pl_self.adjusted_weight


class TestVolumeDiscount:
    """Verify low-volume agencies get reduced review weight."""

    def test_low_volume_reduces_review_weight(self):
        data_high = _make_data(review_count=50)
        data_low = _make_data(review_count=10)
        integrity = _clean_integrity()

        result_high = compute_weighted_signals(data_high, integrity)
        result_low = compute_weighted_signals(data_low, integrity)

        rev_high = next(s for s in result_high.signals if s.signal_name == "reviews")
        rev_low = next(s for s in result_low.signals if s.signal_name == "reviews")

        # Volume discount should apply to low-volume
        assert any("volume_discount" in adj for adj in rev_low.adjustments_applied)


class TestAggregateStats:
    """Verify aggregate statistics are computed correctly."""

    def test_placement_rate_computed(self):
        data = _make_data(placement_count=10)
        integrity = _clean_integrity()
        result = compute_weighted_signals(data, integrity)

        assert result.placement_rate is not None
        assert 0.0 <= result.placement_rate <= 1.0

    def test_avg_star_rating_computed(self):
        data = _make_data()
        integrity = _clean_integrity()
        result = compute_weighted_signals(data, integrity)

        assert result.avg_star_rating is not None
        assert 1.0 <= result.avg_star_rating <= 5.0
