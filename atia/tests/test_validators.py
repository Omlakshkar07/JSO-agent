"""
test_validators.py
─────────────────────────────────────────────
Tests for post-LLM validation rules in validators.py.
─────────────────────────────────────────────
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models.internal import RawProfileDraft, SufficiencyResult, IntegrityResult, IntegrityCheckResult
from models.outputs import IntegrityFlag
from utils.validators import validate_and_correct_profile


def _sufficient():
    """Create a sufficient data result."""
    return SufficiencyResult(
        is_sufficient=True, max_confidence="High",
        review_count=100, placement_count=50,
    )


def _insufficient():
    """Create an insufficient data result."""
    return SufficiencyResult(
        is_sufficient=False, max_confidence="N/A",
        review_count=3, placement_count=1,
    )


def _clean_integrity():
    """Create clean integrity (no flags)."""
    return IntegrityResult(checks=[], flags=[], any_p0_flag=False, any_flag=False)


def _p0_integrity():
    """Create integrity result with a P0 flag."""
    flag = IntegrityFlag(
        flag_id="CHECK-A", severity="P0", label="Test",
        description="test", evidence_summary="test",
    )
    return IntegrityResult(checks=[], flags=[flag], any_p0_flag=True, any_flag=True)


def _p1_integrity():
    """Create integrity result with only P1 flag."""
    flag = IntegrityFlag(
        flag_id="CHECK-E", severity="P1", label="Test",
        description="test", evidence_summary="test",
    )
    return IntegrityResult(checks=[], flags=[flag], any_p0_flag=False, any_flag=True)


def _valid_draft(**overrides):
    """Create a valid RawProfileDraft with optional overrides."""
    defaults = {
        "trust_tier": "High",
        "confidence_level": "High",
        "key_strengths": ["Good placements", "Positive reviews", "Responsive"],
        "key_concerns": [],
        "explanation": "This agency demonstrates strong performance across all evaluated signals with a high placement rate and consistently positive reviews " * 2,
        "audience_summaries": {},
    }
    defaults.update(overrides)
    return RawProfileDraft(**defaults)


class TestTierValidation:
    """Validate trust tier enforcement."""

    def test_valid_tier_unchanged(self):
        draft = _valid_draft(trust_tier="High")
        result = validate_and_correct_profile(draft, _sufficient(), _clean_integrity())
        assert result.trust_tier == "High"

    def test_invalid_tier_forced_to_under_review(self):
        draft = _valid_draft(trust_tier="Excellent")
        result = validate_and_correct_profile(draft, _sufficient(), _clean_integrity())
        assert result.trust_tier == "UnderReview"


class TestP0FlagEnforcement:
    """PRD §FR-022: P0 flag → tier MUST be UnderReview."""

    def test_p0_flag_forces_under_review(self):
        draft = _valid_draft(trust_tier="High")
        result = validate_and_correct_profile(draft, _sufficient(), _p0_integrity())
        assert result.trust_tier == "UnderReview"

    def test_already_under_review_stays(self):
        draft = _valid_draft(trust_tier="UnderReview")
        result = validate_and_correct_profile(draft, _sufficient(), _p0_integrity())
        assert result.trust_tier == "UnderReview"


class TestInsufficientDataRules:
    """PRD §FR-021: InsufficientData → confidence = N/A."""

    def test_insufficient_forces_tier_and_confidence(self):
        draft = _valid_draft(trust_tier="High", confidence_level="High")
        result = validate_and_correct_profile(draft, _insufficient(), _clean_integrity())
        assert result.trust_tier == "InsufficientData"
        assert result.confidence_level == "N/A"


class TestConfidenceCeiling:
    """Confidence cannot exceed ceiling set by data volume."""

    def test_medium_ceiling_caps_high_confidence(self):
        medium_ceiling = SufficiencyResult(
            is_sufficient=True, max_confidence="Medium",
            review_count=30, placement_count=10,
        )
        draft = _valid_draft(confidence_level="High")
        result = validate_and_correct_profile(draft, medium_ceiling, _clean_integrity())
        assert result.confidence_level == "Medium"

    def test_confidence_below_ceiling_unchanged(self):
        draft = _valid_draft(confidence_level="Low")
        result = validate_and_correct_profile(draft, _sufficient(), _clean_integrity())
        assert result.confidence_level == "Low"


class TestP1FlagConfidence:
    """Any flag reduces High confidence to Medium."""

    def test_p1_flag_reduces_high_confidence(self):
        draft = _valid_draft(confidence_level="High")
        result = validate_and_correct_profile(draft, _sufficient(), _p1_integrity())
        assert result.confidence_level == "Medium"

    def test_p1_flag_medium_stays_medium(self):
        draft = _valid_draft(confidence_level="Medium")
        result = validate_and_correct_profile(draft, _sufficient(), _p1_integrity())
        assert result.confidence_level == "Medium"


class TestListLimits:
    """Strengths and concerns capped at 3."""

    def test_too_many_strengths_capped(self):
        draft = _valid_draft(key_strengths=["a", "b", "c", "d", "e"])
        result = validate_and_correct_profile(draft, _sufficient(), _clean_integrity())
        assert len(result.key_strengths) == 3

    def test_valid_count_unchanged(self):
        draft = _valid_draft(key_strengths=["a", "b"])
        result = validate_and_correct_profile(draft, _sufficient(), _clean_integrity())
        assert len(result.key_strengths) == 2
