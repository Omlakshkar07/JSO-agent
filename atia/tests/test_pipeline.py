"""
test_pipeline.py
─────────────────────────────────────────────
Integration tests for the full evaluation pipeline.
Uses mocks for Supabase and Anthropic to test the
complete flow from trigger to response.
─────────────────────────────────────────────
"""

import sys
import os
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models.inputs import EvaluationTrigger


def _now():
    return datetime.now(timezone.utc)


def _mock_supabase_data(review_count=30, placement_count=10, placement_outcome="successful"):
    """Build mock Supabase responses for a test agency."""
    # Use varied ratings to avoid CHECK-B uniformity (3.5-5.0 range)
    rating_pool = [3.5, 4.0, 4.0, 4.5, 5.0]
    reviews = [
        {
            "id": f"r{i}",
            "agency_id": "agency_intg_test",
            "reviewer_id": f"u{i}",
            "rating": rating_pool[i % len(rating_pool)],
            "review_text": f"Good experience {i}",
            "created_at": (_now() - timedelta(days=i)).isoformat(),
        }
        for i in range(review_count)
    ]
    placements = [
        {
            "id": f"p{i}",
            "agency_id": "agency_intg_test",
            "candidate_id": f"c{i}",
            "outcome": placement_outcome,
            "placement_source": "platform_tracked",
            "created_at": (_now() - timedelta(days=i * 3)).isoformat(),
        }
        for i in range(placement_count)
    ]
    feedback = [
        {
            "id": f"f{i}",
            "agency_id": "agency_intg_test",
            "score": 4.2,
            "created_at": (_now() - timedelta(days=i * 5)).isoformat(),
        }
        for i in range(5)
    ]
    users = [
        {"id": f"u{i}", "account_age_days": 365}
        for i in range(review_count)
    ]
    agency = {
        "id": "agency_intg_test",
        "name": "Integration Test Agency",
        "registration_date": (_now() - timedelta(days=365)).isoformat(),
        "is_active": True,
    }

    return {
        "agency": agency,
        "reviews": reviews,
        "placements": placements,
        "feedback": feedback,
        "users": users,
    }


def _build_mock_table(mock_data):
    """Build a mock Supabase client that returns table-specific data."""

    def mock_table(table_name):
        mock = MagicMock()

        # Chain pattern: client.table(...).select(...).eq(...).execute()
        chain = MagicMock()
        mock.select.return_value = chain
        chain.eq.return_value = chain
        chain.in_.return_value = chain
        chain.gt.return_value = chain
        chain.order.return_value = chain
        chain.limit.return_value = chain

        result = MagicMock()
        result.count = 0

        if table_name == "agencies":
            result.data = [mock_data["agency"]]
        elif table_name == "reviews":
            result.data = mock_data["reviews"]
        elif table_name == "placements":
            result.data = mock_data["placements"]
        elif table_name == "feedback_ratings":
            result.data = mock_data["feedback"]
        elif table_name == "users":
            result.data = mock_data["users"]
        elif table_name == "trust_profiles":
            result.data = []
        elif table_name == "evaluation_audit_log":
            result.data = [{}]
        else:
            result.data = []

        chain.execute.return_value = result

        # For upsert/insert
        upsert_chain = MagicMock()
        upsert_chain.execute.return_value = MagicMock(data=[{}])
        mock.upsert.return_value = upsert_chain
        mock.insert.return_value = upsert_chain

        return mock

    return mock_table


def _mock_llm_trust_response():
    """Build a valid LLM trust synthesis response."""
    return json.dumps({
        "trust_tier": "High",
        "confidence_level": "High",
        "key_strengths": [
            "Consistently high placement rate",
            "Strong positive review history",
            "Platform-verified outcomes",
        ],
        "key_concerns": [],
        "explanation": (
            "This agency demonstrates excellent performance across all evaluated signals. "
            "With a placement rate exceeding 80% and an average rating of 4.0 stars across "
            "30 reviews, the data consistently supports a high level of trust. No integrity "
            "anomalies were detected in any of the five checks performed."
        ),
        "audience_summaries": {
            "job_seeker": "This agency has a strong track record. Most candidates placed through them report positive experiences, and their placement success rate is well above average.",
            "hr_consultant": "Agency demonstrates consistent performance with an 80%+ placement rate across 10 verified placements. Review sentiment aligns with outcomes. No anomalies detected.",
            "admin": "Full evaluation complete. 30 reviews (avg 4.0), 10 placements (100% success rate, platform-tracked). All 5 integrity checks passed. No flags. Confidence: High. Previous tier: N/A.",
            "licensing": "Agency meets trust requirements for licensing. Trust tier: High with High confidence. No integrity flags. Placement rate: 100% (platform-tracked). Eligible to proceed.",
        },
        "tier_change_note": None,
    })


def _build_mock_client(mock_data):
    """Build a fully mocked Supabase client."""
    mock_client = MagicMock()
    mock_client.table = _build_mock_table(mock_data)
    return mock_client


def _mock_settings():
    """Create a mock Settings object for testing."""
    settings = MagicMock()
    settings.anthropic_api_key = "test-key"
    settings.supabase_url = "https://test.supabase.co"
    settings.supabase_key = "test-service-key"
    settings.llm_model = "test-model"
    settings.llm_timeout_seconds = 30
    settings.llm_max_tokens = 4096
    settings.log_level = "WARNING"
    settings.environment = "test"
    return settings


class TestCleanAgencyPipeline:
    """Integration test: clean agency should get High tier."""

    @patch("config.settings.get_settings")
    @patch("memory.cache_manager.get_supabase_client")
    @patch("data.agency_queries.get_supabase_client")
    @patch("agent.trust_reasoner.call_llm")
    @patch("agent.signal_auditor.call_llm")
    def test_clean_agency_gets_high_tier(
        self, mock_sentiment_llm, mock_trust_llm, mock_db_client, mock_cache_client,
        mock_get_settings,
    ):
        """A well-behaved agency with good data should receive High tier."""
        mock_get_settings.return_value = _mock_settings()

        # Set up mock Supabase
        mock_data = _mock_supabase_data()
        mock_client = _build_mock_client(mock_data)
        mock_db_client.return_value = mock_client
        mock_cache_client.return_value = mock_client

        # Mock sentiment LLM (CHECK-E): all POSITIVE for high-rated reviews
        sentiment_resp = MagicMock()
        sentiment_resp.content = json.dumps([
            {"review_id": f"r{i}", "sentiment": "POSITIVE"} for i in range(20)
        ])
        mock_sentiment_llm.return_value = sentiment_resp

        # Mock trust synthesis LLM
        trust_resp = MagicMock()
        trust_resp.content = _mock_llm_trust_response()
        trust_resp.input_tokens = 1000
        trust_resp.output_tokens = 500
        trust_resp.prompt_hash = "test_hash"
        mock_trust_llm.return_value = trust_resp

        # Run the pipeline
        from agent.orchestrator import run_evaluation

        trigger = EvaluationTrigger(
            agency_id="agency_intg_test",
            trigger_type="ON_DEMAND",
            requestor_role="job_seeker",
            force_refresh=True,
        )

        result = run_evaluation(trigger)

        # Verify results
        assert result.trust_tier == "High"
        assert result.confidence_level == "High"
        assert len(result.integrity_flags) == 0  # job_seeker doesn't see flags


class TestInsufficientDataPipeline:
    """Integration test: new agency should get InsufficientData tier."""

    @patch("config.settings.get_settings")
    @patch("memory.cache_manager.get_supabase_client")
    @patch("data.agency_queries.get_supabase_client")
    def test_new_agency_gets_insufficient_data(
        self, mock_db_client, mock_cache_client, mock_get_settings,
    ):
        """Agency with too little data → InsufficientData, no LLM call."""
        mock_get_settings.return_value = _mock_settings()

        # Mock with very little data (3 reviews, 1 placement)
        mock_data = _mock_supabase_data(review_count=3, placement_count=1)

        mock_client = _build_mock_client(mock_data)
        mock_db_client.return_value = mock_client
        mock_cache_client.return_value = mock_client

        from agent.orchestrator import run_evaluation

        trigger = EvaluationTrigger(
            agency_id="agency_intg_test",
            trigger_type="ON_DEMAND",
            requestor_role="admin",
            force_refresh=True,
        )

        result = run_evaluation(trigger)

        assert result.trust_tier == "InsufficientData"
        assert result.confidence_level == "N/A"
