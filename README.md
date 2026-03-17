<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/Next.js-16-000000?style=for-the-badge&logo=next.js&logoColor=white" />
  <img src="https://img.shields.io/badge/Claude-Sonnet_4-D97757?style=for-the-badge&logo=anthropic&logoColor=white" />
  <img src="https://img.shields.io/badge/Supabase-PostgreSQL-3FCF8E?style=for-the-badge&logo=supabase&logoColor=white" />
  <img src="https://img.shields.io/badge/License-Proprietary-red?style=for-the-badge" />
</p>

<h1 align="center">🛡️ ATIA — Agency Trust & Transparency Agent</h1>

<p align="center">
  <strong>AI-powered trust evaluation engine for recruitment agencies</strong><br/>
  Multi-signal analysis · Manipulation detection · Audience-aware reporting
</p>

<p align="center">
  <a href="#-architecture">Architecture</a> •
  <a href="#-features">Features</a> •
  <a href="#-getting-started">Getting Started</a> •
  <a href="#-api-reference">API Reference</a> •
  <a href="#-project-structure">Project Structure</a> •
  <a href="#-testing">Testing</a>
</p>

---

## 📋 Overview

**ATIA** (Agency Trust & Transparency Agent) is an intelligent evaluation system designed to assess the trustworthiness of recruitment agencies using multi-signal analysis, LLM-powered reasoning, and real-time manipulation detection.

The system ingests data from **reviews**, **placements**, and **feedback ratings**, runs it through a **5-step integrity check pipeline**, applies **weighted signal scoring**, and synthesizes a comprehensive **trust profile** using **Anthropic Claude**. Results are delivered through **audience-aware summaries** tailored to four distinct user roles.

> **Built for [JSO (Job Seeker Operations)](https://jso.com)** — ensuring recruitment agencies are transparent, accountable, and trustworthy.

---

## ✨ Features

### 🤖 Intelligent Trust Evaluation
- **8-step evaluation pipeline** — from trigger to audience-specific response delivery
- **LLM-powered synthesis** using Anthropic Claude (Sonnet 4) for trust tier determination
- **Five trust tiers**: `High` · `Medium` · `Low` · `UnderReview` · `InsufficientData`
- **Confidence assessment**: `High` · `Medium` · `Low` · `N/A`

### 🔍 Manipulation Detection (5 Integrity Checks)
| Check | Name | Severity | Detection Logic |
|-------|------|----------|-----------------|
| **CHECK-A** | Review Velocity Anomaly | P0 | Flags if 14-day daily avg > 3× the 90-day baseline |
| **CHECK-B** | Rating Uniformity Anomaly | P0 | Flags if ≥95% of ratings in 30 days are identical |
| **CHECK-C** | Reviewer Account Age Anomaly | P0 | Flags if ≥40% of recent reviewers are <30 days old |
| **CHECK-D** | Cross-Signal Inconsistency | P0 | Flags if high sentiment but <20% placement rate |
| **CHECK-E** | Sentiment-Rating Mismatch | P1 | LLM-assessed: flags if ≥30% reviews contradict stars |

### 👥 Audience-Aware Responses
- **Job Seekers** — Empathetic, plain-English summaries (40–80 words)
- **HR Consultants** — Professional, benchmarked insights (60–100 words)
- **Admins** — Technical, complete, unfiltered analysis (100–200 words)
- **Licensing Bodies** — Formal, decision-ready with PASS/FAIL indicators

### ⚡ Performance & Resilience
- **Smart caching** — 24-hour profile cache with event-based invalidation
- **Graceful degradation** — stale cache served up to 72h on pipeline failure
- **Rate limiting** — 1 evaluation per agency per 15 minutes
- **Structured JSON logging** — every evaluation logged with full audit trail

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    ATIA SYSTEM ARCHITECTURE                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐     ┌──────────────────────────────────────┐  │
│  │   Frontend   │     │          FastAPI Backend              │  │
│  │  (Next.js)   │────▶│                                      │  │
│  │  Port: 3000  │     │  ┌────────────────────────────────┐  │  │
│  └──────────────┘     │  │      API Layer (routes.py)     │  │  │
│                       │  │  • Trust Profiles  • Overrides  │  │  │
│                       │  │  • Evaluations    • Anomalies   │  │  │
│                       │  └────────────┬───────────────────┘  │  │
│                       │               │                      │  │
│                       │  ┌────────────▼───────────────────┐  │  │
│                       │  │    Orchestrator (8-step pipe)   │  │  │
│                       │  └──┬─────┬──────┬──────┬────────┘  │  │
│                       │     │     │      │      │            │  │
│                       │  ┌──▼──┐┌─▼───┐┌─▼───┐┌─▼────────┐  │  │
│                       │  │Audit││Wght ││Trust││ Responder │  │  │
│                       │  │ or  ││ Eng ││Rsnr ││           │  │  │
│                       │  └─────┘└─────┘└──┬──┘└───────────┘  │  │
│                       │                   │                  │  │
│                       │            ┌──────▼──────┐           │  │
│                       │            │  Claude LLM │           │  │
│                       │            │  (Anthropic) │           │  │
│                       │            └─────────────┘           │  │
│                       │                                      │  │
│                       │  ┌────────────────────────────────┐  │  │
│                       │  │         Data Layer             │  │  │
│                       │  │  Supabase (PostgreSQL + Auth)  │  │  │
│                       │  └────────────────────────────────┘  │  │
│                       └──────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Evaluation Pipeline (Steps 1–8)

```
Trigger ──▶ Cache ──▶ Data ──▶ Sufficiency ──▶ Integrity ──▶ Weighting ──▶ LLM ──▶ Response
  (1)       Check    Fetch      Check          Checks        Engine      Synth    Delivery
             (1)      (2)        (3)            (4)           (5)        (6-7)      (8)
```

---

## 🚀 Getting Started

### Prerequisites

| Requirement | Version |
|------------|---------|
| Python | 3.12+ |
| Node.js | 18+ |
| npm | 9+ |

You will also need:
- **Anthropic API Key** — for Claude LLM access ([get one here](https://console.anthropic.com/))
- **Supabase Project** — for PostgreSQL database + Auth ([create one here](https://supabase.com/))

### 1. Clone the Repository

```bash
git clone https://github.com/Omlakshkar07/JSO-agent.git
cd "JSO assignment"
```

### 2. Backend Setup

```bash
cd atia

# Create virtual environment
python -m venv venv
venv\Scripts\activate         # Windows
# source venv/bin/activate    # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

#### Configure Environment Variables

Create a `.env` file in the `atia/` directory:

```env
# ─── Anthropic (Required) ───────────────────
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxx

# ─── Supabase (Required) ────────────────────
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key

# ─── Application (Optional) ─────────────────
LLM_MODEL=claude-sonnet-4-20250514
LOG_LEVEL=INFO
ENVIRONMENT=development
API_HOST=0.0.0.0
API_PORT=8000
```

#### Run the Backend

```bash
python main.py
# or
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

### 3. Frontend Setup

```bash
cd atia-dashboard

# Install dependencies
npm install
```

#### Configure Frontend Environment

Create a `.env.local` file in the `atia-dashboard/` directory:

```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
NEXT_PUBLIC_API_URL=http://localhost:8000
```

#### Run the Frontend

```bash
npm run dev
```

The dashboard will be available at `http://localhost:3000`

---

## 📡 API Reference

All endpoints are prefixed with `/api/v1/agent`

### Trust Profiles

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/trust-profile/{agency_id}` | All roles | Get trust profile for an agency |
| `GET` | `/trust-profile/{agency_id}/history` | Admin, HR | Trust tier change history |
| `GET` | `/trust-profile/{agency_id}/audit` | Admin only | Full evaluation audit trail |

### Evaluations

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/evaluate/{agency_id}` | Admin only | Trigger on-demand evaluation |

### Admin Operations

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/override/{agency_id}` | Admin only | Override trust tier (with reason) |
| `GET` | `/anomaly-queue` | Admin only | List agencies with P0 integrity flags |
| `GET` | `/agencies` | All roles | List all agencies with profiles |

### Health Check

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/health` | None | Basic service health check |

### Example Request

```bash
# Get trust profile (as admin)
curl -X GET http://localhost:8000/api/v1/agent/trust-profile/{agency_id} \
  -H "X-User-Role: admin" \
  -H "X-User-Id: user-uuid-here"
```

### Example Response

```json
{
  "agency_id": "550e8400-e29b-41d4-a716-446655440000",
  "trust_tier": "High",
  "confidence_level": "Medium",
  "key_strengths": [
    "Consistently high placement success rate",
    "Strong positive review sentiment",
    "Long platform tenure with steady growth"
  ],
  "key_concerns": [],
  "integrity_flags": [],
  "summary": "This agency demonstrates strong trustworthiness...",
  "tier_change_note": null,
  "evaluated_at": "2026-03-17T10:30:00Z",
  "data_is_stale": false
}
```

---

## 📁 Project Structure

```
JSO assignment/
│
├── atia/                          # 🐍 Backend (FastAPI + Python)
│   ├── main.py                    # Application entry point
│   ├── requirements.txt           # Python dependencies
│   ├── .env                       # Environment variables (not committed)
│   │
│   ├── agent/                     # 🤖 Core AI Agent Logic
│   │   ├── orchestrator.py        # 8-step evaluation pipeline controller
│   │   ├── signal_auditor.py      # Sub-Agent A: 5 integrity checks
│   │   ├── weighting_engine.py    # Signal weight computation & normalization
│   │   ├── trust_reasoner.py      # Sub-Agent B: LLM trust synthesis
│   │   └── responder.py           # Audience-aware response formatting
│   │
│   ├── api/                       # 🌐 API Layer
│   │   ├── routes.py              # All REST endpoint handlers
│   │   ├── middleware.py          # Auth, RBAC, rate limiting
│   │   └── event_listener.py      # Supabase Realtime event handlers
│   │
│   ├── config/                    # ⚙️ Configuration
│   │   ├── constants.py           # All thresholds, enums, magic numbers
│   │   └── settings.py            # Runtime env var loading (Pydantic)
│   │
│   ├── data/                      # 💾 Data Access Layer
│   │   ├── agency_queries.py      # Supabase CRUD operations
│   │   └── supabase_client.py     # Database client singleton
│   │
│   ├── llm/                       # 🧠 LLM Integration
│   │   ├── client.py              # Anthropic API wrapper with retries
│   │   ├── prompts.py             # Prompt templates for Claude
│   │   └── parser.py              # LLM response JSON parsing
│   │
│   ├── memory/                    # 🗄️ Caching Layer
│   │   └── cache_manager.py       # Profile cache with TTL & invalidation
│   │
│   ├── models/                    # 📦 Data Models (Pydantic)
│   │   ├── inputs.py              # Request & raw data schemas
│   │   ├── outputs.py             # Response & trust profile schemas
│   │   └── internal.py            # Pipeline intermediate data models
│   │
│   ├── utils/                     # 🔧 Utilities
│   │   ├── error_handler.py       # Custom exception hierarchy
│   │   ├── logger.py              # Structured JSON logging
│   │   └── validators.py          # Post-LLM profile validation
│   │
│   ├── tests/                     # ✅ Test Suite
│   │   ├── test_integrity_checks.py
│   │   ├── test_weighting_engine.py
│   │   ├── test_validators.py
│   │   └── test_pipeline.py
│   │
│   └── scripts/                   # 📜 Utility Scripts
│       ├── setup_database.py      # Database schema initialization
│       └── test_connection.py     # Connection verification
│
├── atia-dashboard/                # ⚛️ Frontend (Next.js 16)
│   ├── src/                       # Application source code
│   ├── public/                    # Static assets
│   ├── package.json               # Node.js dependencies
│   └── tailwind.config.ts         # Tailwind CSS configuration
│
├── ATIA_PRD_v1.0.docx             # 📄 Product Requirements Document
└── JSO_Agentic_Assignment.docx    # 📄 Assignment Specification
```

---

## 🧪 Testing

```bash
cd atia

# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_integrity_checks.py

# Run specific test
pytest tests/test_weighting_engine.py::test_normalize_weights
```

### Test Coverage

| Test File | Covers |
|-----------|--------|
| `test_integrity_checks.py` | All 5 integrity checks (CHECK-A through CHECK-E) |
| `test_weighting_engine.py` | Weight computation, normalization, adjustments |
| `test_validators.py` | Post-LLM profile validation & correction |
| `test_pipeline.py` | End-to-end evaluation pipeline |

---

## 🗃️ Database Schema

ATIA uses **Supabase** (PostgreSQL) with the following core tables:

| Table | Purpose |
|-------|---------|
| `agencies` | Agency registration data and metadata |
| `reviews` | Individual reviews submitted for agencies |
| `placements` | Placement records (successful/unsuccessful) |
| `feedback_ratings` | Numeric feedback scores |
| `users` | User accounts with account age for CHECK-C |
| `trust_profiles` | Computed trust profiles (upserted per agency) |
| `evaluation_audit_log` | Immutable audit trail (append-only) |

> Run `python scripts/setup_database.py` to initialize the database schema.

---

## 🔒 Security

- **Role-based access control** — endpoints restricted by user role
- **JWT authentication** — Supabase Auth tokens (dev mode: `X-User-Role` header)
- **Rate limiting** — prevents evaluation spam (15-minute cooldown per agency)
- **PII protection** — reviewer IDs stripped before LLM calls
- **Immutable audit log** — no UPDATE or DELETE on audit records
- **Prompt hashing** — SHA-256 hash of every LLM prompt for reproducibility
- **Error sanitization** — raw errors never exposed to users

---

## ⚙️ Configuration Reference

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | ✅ | — | Anthropic API key |
| `SUPABASE_URL` | ✅ | — | Supabase project URL |
| `SUPABASE_KEY` | ✅ | — | Supabase service role key |
| `LLM_MODEL` | ❌ | `claude-sonnet-4-20250514` | Claude model identifier |
| `LLM_TIMEOUT_SECONDS` | ❌ | `30` | Max LLM response wait time |
| `LLM_MAX_TOKENS` | ❌ | `4096` | Max tokens for LLM response |
| `LOG_LEVEL` | ❌ | `INFO` | Logging verbosity |
| `ENVIRONMENT` | ❌ | `development` | Runtime environment |
| `API_HOST` | ❌ | `0.0.0.0` | API bind host |
| `API_PORT` | ❌ | `8000` | API bind port |

### Key Thresholds

| Parameter | Value | Purpose |
|-----------|-------|---------|
| Cache TTL | 24 hours | Fresh profile serving window |
| Stale Cache Max | 72 hours | Fallback serving window on errors |
| Min Reviews | 10 | Minimum for trust evaluation |
| Min Placements | 5 | Minimum for trust evaluation |
| Signal Weights | 40/40/20 | Reviews / Placements / Ratings |
| Override Reason | 20 chars min | Admin override justification |

---

## 🛠 Tech Stack

### Backend
| Technology | Purpose |
|-----------|---------|
| **FastAPI** `0.115` | High-performance async API framework |
| **Pydantic** `2.10` | Data validation & settings management |
| **Anthropic SDK** `0.44` | Claude LLM integration |
| **Supabase** `2.11` | PostgreSQL database + realtime events |
| **Uvicorn** `0.34` | ASGI server |
| **Pytest** `8.3` | Testing framework |

### Frontend
| Technology | Purpose |
|-----------|---------|
| **Next.js** `16` | React framework with SSR |
| **React** `19` | UI component library |
| **Tailwind CSS** `4` | Utility-first CSS framework |
| **Recharts** `3.8` | Data visualization & charts |
| **React Query** `5` | Server state management |
| **Supabase SSR** | Auth & realtime client |

---

## 📄 License

This project is proprietary and developed as part of the **JSO Agentic Assignment**.

---

<p align="center">
  <strong>Built with 🤖 by the ATIA Team</strong><br/>
  <sub>Powered by Anthropic Claude · Supabase · FastAPI · Next.js</sub>
</p>
