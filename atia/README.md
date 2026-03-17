# ATIA — Agency Trust & Transparency Agent

An AI agent for the JSO recruitment platform that evaluates agency trustworthiness through multi-signal analysis and manipulation detection.

## What It Does

ATIA analyzes reviews, placements, and feedback to produce honest trust profiles. It detects 5 types of manipulation patterns and delivers audience-appropriate assessments to job seekers, HR consultants, admins, and licensing reviewers.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Anthropic API key and Supabase credentials

# Run the server
python main.py
```

The API server starts at `http://localhost:8000`. Visit `/docs` for interactive Swagger documentation.

## API Endpoints

| Method | Path | Access | Description |
|--------|------|--------|-------------|
| GET | `/api/v1/agent/trust-profile/{agency_id}` | All roles | Retrieve trust profile |
| POST | `/api/v1/agent/evaluate/{agency_id}` | Admin only | Trigger fresh evaluation |
| GET | `/api/v1/agent/trust-profile/{agency_id}/audit` | Admin only | Full audit trail |
| POST | `/api/v1/agent/override/{agency_id}` | Admin only | Override trust tier |
| GET | `/api/v1/agent/anomaly-queue` | Admin only | Agencies with P0 flags |
| GET | `/api/v1/agent/trust-profile/{agency_id}/history` | Admin/HR | Tier change history |

## Architecture

```
main.py ← Entry point only
│
├── agent/              ← Agent core (pipeline logic)
│   ├── orchestrator    ← Steps 1-8 pipeline controller
│   ├── signal_auditor  ← Sub-Agent A: 5 integrity checks
│   ├── weighting_engine← Signal weight calculations
│   ├── trust_reasoner  ← Sub-Agent B: LLM trust synthesis
│   └── responder       ← Audience-aware formatting
│
├── api/                ← HTTP layer
│   ├── routes          ← FastAPI endpoint handlers
│   ├── middleware       ← Auth, rate limiting
│   └── event_listener  ← Supabase Realtime triggers
│
├── data/               ← Database access
│   ├── supabase_client ← Connection singleton
│   └── agency_queries  ← All Supabase queries
│
├── llm/                ← LLM integration
│   ├── prompts         ← All prompts (centralized)
│   ├── client          ← Anthropic API wrapper
│   └── parser          ← Defensive JSON parsing
│
├── memory/             ← Caching
│   └── cache_manager   ← Profile cache logic
│
├── models/             ← Data shapes
│   ├── inputs          ← Evaluation triggers, raw data
│   ├── outputs         ← Trust profiles, audit logs
│   └── internal        ← Pipeline intermediates
│
├── config/             ← Configuration
│   ├── constants       ← All thresholds and magic numbers
│   └── settings        ← Environment variables
│
└── utils/              ← Utilities
    ├── logger          ← Structured JSON logging
    ├── error_handler   ← Custom exception hierarchy
    └── validators      ← Post-LLM rule enforcement
```

## Trust Tiers

| Tier | Meaning |
|------|---------|
| **High** | Strong track record across all signals |
| **Medium** | Acceptable performance with minor concerns |
| **Low** | Significant concerns identified |
| **UnderReview** | Forced by P0 integrity flags (manipulation detected) |
| **InsufficientData** | Not enough data for a reliable assessment |

## Integrity Checks

| Check | Detects | Severity |
|-------|---------|----------|
| CHECK-A | Review velocity spike (>3× baseline) | P0 |
| CHECK-B | Rating uniformity (>95% identical) | P0 |
| CHECK-C | New account reviewers (>40% under 30d) | P0 |
| CHECK-D | Cross-signal inconsistency | P0 |
| CHECK-E | Sentiment-rating mismatch (LLM) | P1 |

## Running Tests

```bash
pytest tests/ -v
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API key |
| `SUPABASE_URL` | Yes | — | Supabase project URL |
| `SUPABASE_KEY` | Yes | — | Supabase service role key |
| `LLM_MODEL` | No | `claude-sonnet-4-20250514` | Claude model ID |
| `LLM_TIMEOUT_SECONDS` | No | 30 | LLM timeout |
| `LOG_LEVEL` | No | INFO | Logging level |
| `ENVIRONMENT` | No | development | Runtime environment |
