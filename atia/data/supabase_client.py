"""
supabase_client.py
─────────────────────────────────────────────
PURPOSE:
  Singleton Supabase client connection. All database access
  flows through this module — no other file creates a
  Supabase client directly.

RESPONSIBILITIES:
  - Create and cache a single Supabase client instance
  - Expose the client for use by data query modules

NOT RESPONSIBLE FOR:
  - Writing specific queries (see agency_queries.py)
  - Business logic of any kind

DEPENDENCIES:
  - supabase: official Python SDK
  - config.settings: URL and key

USED BY:
  - data/agency_queries.py
  - memory/cache_manager.py
─────────────────────────────────────────────
"""

from functools import lru_cache

from supabase import create_client, Client

from config.settings import get_settings


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """
    Return the singleton Supabase client.

    Uses lru_cache so the connection is created exactly once.
    Subsequent calls return the same client instance.

    Returns:
        An authenticated Supabase Client.

    Raises:
        Exception: If SUPABASE_URL or SUPABASE_KEY is invalid.
    """
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_key)
