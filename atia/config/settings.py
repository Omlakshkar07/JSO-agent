"""
settings.py
─────────────────────────────────────────────
PURPOSE:
  Runtime configuration loaded from environment variables.
  Uses Pydantic Settings to validate and provide typed access
  to all configuration values. Fails fast on startup if
  required values are missing.

RESPONSIBILITIES:
  - Load all env vars with validation
  - Provide a singleton Settings instance
  - Define sensible defaults where appropriate

NOT RESPONSIBLE FOR:
  - Hardcoded thresholds (see constants.py)
  - Business logic of any kind

DEPENDENCIES:
  - pydantic_settings: env var loading

USED BY:
  - Every module that needs runtime config
─────────────────────────────────────────────
"""

import os
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings
from pydantic import Field

# Project root = the directory containing this config/ package
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """
    All runtime configuration for the ATIA agent.

    Values are loaded from environment variables (or .env file).
    Required fields have no default — app will not start without them.
    """

    # ─── Anthropic LLM ──────────────────────────────────────
    anthropic_api_key: str = Field(
        ...,
        description="Anthropic API key. Never log this value.",
    )
    llm_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Claude model identifier. Change to swap models.",
    )
    llm_timeout_seconds: int = Field(
        default=30,
        description="Max seconds to wait for an LLM response.",
    )
    llm_max_tokens: int = Field(
        default=4096,
        description="Max tokens for LLM response generation.",
    )

    # ─── Supabase ───────────────────────────────────────────
    supabase_url: str = Field(
        ...,
        description="Supabase project URL (https://xxx.supabase.co).",
    )
    supabase_key: str = Field(
        ...,
        description="Supabase service role key for server-side access.",
    )

    # ─── Application ────────────────────────────────────────
    log_level: str = Field(
        default="INFO",
        description="Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL.",
    )
    environment: str = Field(
        default="development",
        description="Runtime environment: development, staging, production.",
    )
    api_host: str = Field(
        default="0.0.0.0",
        description="Host to bind the API server to.",
    )
    api_port: int = Field(
        default=8000,
        description="Port to bind the API server to.",
    )

    model_config = {
        "env_file": str(ENV_FILE_PATH),
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the singleton Settings instance.

    Uses lru_cache to ensure settings are loaded exactly once.
    Call this function wherever you need config — never
    instantiate Settings directly.

    Returns:
        The validated Settings object.

    Raises:
        ValidationError: if required env vars are missing.
    """
    return Settings()
