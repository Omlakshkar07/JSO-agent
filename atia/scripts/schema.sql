-- ─────────────────────────────────────────────
-- ATIA Complete Schema
-- Run this in the Supabase SQL Editor
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.agencies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  registration_date timestamptz NOT NULL DEFAULT now(),
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text,
  role text NOT NULL DEFAULT 'job_seeker',
  account_age_days integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Note: we use IF NOT EXISTS, so running this multiple times is safe.
CREATE TABLE IF NOT EXISTS public.reviews (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agency_id uuid NOT NULL REFERENCES public.agencies(id) ON DELETE CASCADE,
  reviewer_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  rating numeric(2,1) NOT NULL CHECK (rating >= 1.0 AND rating <= 5.0),
  review_text text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reviews_agency_id ON public.reviews(agency_id);
CREATE INDEX IF NOT EXISTS idx_reviews_created_at ON public.reviews(created_at);

CREATE TABLE IF NOT EXISTS public.placements (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agency_id uuid NOT NULL REFERENCES public.agencies(id) ON DELETE CASCADE,
  candidate_id uuid,
  outcome text NOT NULL CHECK (outcome IN ('successful', 'unsuccessful')),
  placement_source text NOT NULL DEFAULT 'self_reported' CHECK (placement_source IN ('platform_tracked', 'self_reported')),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_placements_agency_id ON public.placements(agency_id);

CREATE TABLE IF NOT EXISTS public.feedback_ratings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agency_id uuid NOT NULL REFERENCES public.agencies(id) ON DELETE CASCADE,
  score numeric(2,1) NOT NULL CHECK (score >= 1.0 AND score <= 5.0),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_feedback_agency_id ON public.feedback_ratings(agency_id);

CREATE TABLE IF NOT EXISTS public.trust_profiles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agency_id uuid NOT NULL UNIQUE REFERENCES public.agencies(id) ON DELETE CASCADE,
  trust_tier text NOT NULL CHECK (trust_tier IN ('High','Medium','Low','UnderReview','InsufficientData')),
  confidence_level text NOT NULL CHECK (confidence_level IN ('High','Medium','Low','N/A')),
  key_strengths jsonb NOT NULL DEFAULT '[]'::jsonb,
  key_concerns jsonb NOT NULL DEFAULT '[]'::jsonb,
  integrity_flags jsonb NOT NULL DEFAULT '[]'::jsonb,
  signal_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  explanation text NOT NULL DEFAULT '',
  audience_summaries jsonb NOT NULL DEFAULT '{}'::jsonb,
  previous_tier text,
  tier_change_note text,
  evaluated_at timestamptz NOT NULL DEFAULT now(),
  evaluation_trigger text NOT NULL DEFAULT 'ON_DEMAND',
  data_window_start timestamptz,
  llm_model_version text NOT NULL DEFAULT '',
  data_is_stale boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.evaluation_audit_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agency_id uuid NOT NULL REFERENCES public.agencies(id) ON DELETE CASCADE,
  trust_profile_id uuid,
  evaluation_trigger text NOT NULL,
  triggered_by text,
  raw_signal_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  integrity_checks_log jsonb NOT NULL DEFAULT '{}'::jsonb,
  weighted_signals jsonb NOT NULL DEFAULT '{}'::jsonb,
  llm_prompt_hash text NOT NULL DEFAULT '',
  llm_response_raw text NOT NULL DEFAULT '',
  final_trust_tier text NOT NULL DEFAULT '',
  final_confidence text NOT NULL DEFAULT '',
  override_applied boolean NOT NULL DEFAULT false,
  override_by text,
  override_reason text,
  override_tier text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_agency_id ON public.evaluation_audit_log(agency_id);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON public.evaluation_audit_log(created_at);

-- Optional: Force postgrest schema reload
NOTIFY pgrst, 'reload schema';
