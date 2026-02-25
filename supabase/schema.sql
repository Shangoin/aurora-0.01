-- ============================================================
-- Shango Revenue Systems — Complete Supabase Schema
-- Run this in Supabase SQL Editor once
-- ============================================================

-- Enable pgcrypto for UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- TABLE: leads
-- Stores every inbound lead from the landing page
-- ============================================================
CREATE TABLE IF NOT EXISTS leads (
    id            UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT UNIQUE NOT NULL,
    phone         TEXT,
    company       TEXT,
    lead_volume   TEXT,          -- "1-10", "10-50", "50-200", "200+"
    message       TEXT,
    -- AI Scoring
    score             INTEGER DEFAULT 0 CHECK (score >= 0 AND score <= 100),
    tier              TEXT DEFAULT 'unscored' CHECK (tier IN ('high','medium','low','unscored')),
    score_reasoning   TEXT,
    icp_fit           BOOLEAN DEFAULT FALSE,
    budget_signals    JSONB DEFAULT '[]',
    -- Serper enrichment (populated by enrichment.py on every lead submission)
    enrichment_signals JSONB DEFAULT '{}',
    -- Status
    status        TEXT DEFAULT 'new' CHECK (status IN (
                    'new','call_initiated','call_completed',
                    'meeting_booked','follow_up_needed',
                    'nurture_queue','closed_lost','not_active')),
    -- Post-call enrichment
    pain_points         JSONB DEFAULT '[]',
    deal_probability    INTEGER DEFAULT 0,
    buying_stage        TEXT,
    last_call_score     INTEGER DEFAULT 0,
    follow_up_type      TEXT,
    next_touch_at       TIMESTAMPTZ,
    -- Metadata
    source        TEXT DEFAULT 'landing_page',
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast status queries
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_tier ON leads(tier);
CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at DESC);

-- ============================================================
-- TABLE: calls
-- Stores every Vapi call with full critique
-- ============================================================
CREATE TABLE IF NOT EXISTS calls (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    call_id             TEXT UNIQUE,             -- Vapi call ID
    lead_email          TEXT REFERENCES leads(email) ON DELETE SET NULL,
    -- Call data
    transcript          TEXT,
    recording_url       TEXT,
    duration_seconds    INTEGER DEFAULT 0,
    cost_usd            NUMERIC(8,4) DEFAULT 0,
    ended_reason        TEXT,
    -- AI Critique Scores (0-100 each)
    overall_score       INTEGER DEFAULT 0,
    opening_score       INTEGER DEFAULT 0,
    discovery_score     INTEGER DEFAULT 0,
    rapport_score       INTEGER DEFAULT 0,
    objection_score     INTEGER DEFAULT 0,
    closing_score       INTEGER DEFAULT 0,
    naturalness_score   INTEGER DEFAULT 0,
    relevance_score     INTEGER DEFAULT 0,
    -- Outcomes
    meeting_booked      BOOLEAN DEFAULT FALSE,
    should_follow_up    BOOLEAN DEFAULT FALSE,
    follow_up_strategy  TEXT CHECK (follow_up_strategy IN ('email','call','whatsapp','sms','none')),
    -- Structured insights
    pain_points         JSONB DEFAULT '[]',
    action_items        JSONB DEFAULT '[]',
    script_improvements JSONB DEFAULT '[]',
    full_critique       JSONB,
    one_line_summary    TEXT,
    sentiment           TEXT,
    buying_stage        TEXT,
    deal_probability    INTEGER DEFAULT 0,
    -- Metadata
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_calls_lead ON calls(lead_email);
CREATE INDEX IF NOT EXISTS idx_calls_created_at ON calls(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_calls_score ON calls(overall_score DESC);

-- ============================================================
-- TABLE: agent_improvements
-- Queue of pending script improvements from critique
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_improvements (
    id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    improvement_type    TEXT NOT NULL,   -- 'script', 'objection', 'opening', 'closing'
    source_call_id      TEXT,            -- Vapi call ID
    current_behavior    TEXT,
    suggested_behavior  TEXT,
    example_script      TEXT,
    impact              TEXT CHECK (impact IN ('high','medium','low')),
    status              TEXT DEFAULT 'pending_review' CHECK (
                          status IN ('pending_review','applied','rejected')),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_improvements_status ON agent_improvements(status);
CREATE INDEX IF NOT EXISTS idx_improvements_impact ON agent_improvements(impact);

-- ============================================================
-- TABLE: prompt_versions
-- History of all Vapi agent prompts
-- ============================================================
CREATE TABLE IF NOT EXISTS prompt_versions (
    id                      UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    version                 INTEGER UNIQUE NOT NULL,
    prompt_text             TEXT NOT NULL,
    changelog               TEXT,
    based_on_calls          INTEGER DEFAULT 0,
    avg_score_before        NUMERIC(5,2),
    avg_score_after         NUMERIC(5,2),
    is_active               BOOLEAN DEFAULT TRUE,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TABLE: audit_log
-- Immutable trace of every system decision (governance)
-- ============================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id          UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    event_type  TEXT NOT NULL,   -- 'lead_scored','call_initiated','critique_run','prompt_updated'
    entity_id   TEXT,
    entity_type TEXT,
    payload     JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);

-- ============================================================
-- TABLE: daily_stats
-- Pre-aggregated daily metrics for fast dashboard queries
-- ============================================================
CREATE TABLE IF NOT EXISTS daily_stats (
    id              UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    stat_date       DATE UNIQUE NOT NULL,
    leads_captured  INTEGER DEFAULT 0,
    calls_made      INTEGER DEFAULT 0,
    meetings_booked INTEGER DEFAULT 0,
    avg_call_score  NUMERIC(5,2) DEFAULT 0,
    total_cost_usd  NUMERIC(8,4) DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- FUNCTION: auto-update updated_at on leads
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE OR REPLACE TRIGGER update_leads_updated_at
    BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();

-- ============================================================
-- ROW LEVEL SECURITY (Service role bypasses RLS)
-- ============================================================
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_improvements ENABLE ROW LEVEL SECURITY;
ALTER TABLE prompt_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_stats ENABLE ROW LEVEL SECURITY;

-- Allow service role full access
CREATE POLICY "service_all" ON leads FOR ALL USING (true);
CREATE POLICY "service_all" ON calls FOR ALL USING (true);
CREATE POLICY "service_all" ON agent_improvements FOR ALL USING (true);
CREATE POLICY "service_all" ON prompt_versions FOR ALL USING (true);
CREATE POLICY "service_all" ON audit_log FOR ALL USING (true);
CREATE POLICY "service_all" ON daily_stats FOR ALL USING (true);

-- ============================================================
-- SEED: Initial Vapi prompt (version 1)
-- ============================================================
INSERT INTO prompt_versions (version, prompt_text, changelog, is_active)
VALUES (
    1,
    E'You are ARIA, an elite AI sales development representative from Shango Revenue Systems. Your only goal is to book a discovery call with qualified prospects.\n\nPERSONA: You are warm, confident, and genuinely curious. You have done your homework on the prospect\'s business. You are NOT pushy or salesy.\n\nOPENING (always start here):\n"Hi [name], this is ARIA calling from Shango Revenue Systems. I saw you filled out our form about [their use case]. Is now a good time for 2 minutes?"\n\nDISCOVERY QUESTIONS (ask max 3, listen intently):\n1. "What made you reach out today — what\'s the biggest challenge you\'re trying to solve?"\n2. "How are you handling that right now, and what\'s not working?"\n3. "If you could solve this perfectly, what would that look like 90 days from now?"\n\nVALUE POSITIONING (only after discovery):\nTie your solution directly to their specific pain point. Use their exact words.\n\nOBJECTION HANDLING:\n- "Not interested": "Totally understand. Just out of curiosity, what would need to be different for it to make sense?"\n- "Too expensive": "Makes sense to ask. Quick question — what\'s the cost each month of NOT solving [their pain]?"\n- "Send me info": "Happy to. Let me ask one quick thing first — [discovery question]"\n- "Talk to my boss": "Absolutely. Would it help if I walked through the key points with both of you?"\n\nCLOSING:\n"Based on what you\'ve shared, I think a 20-minute demo would be worth your time. I have [time slot] or [time slot] — which works better?"\n\nRULES:\n- Never lie or exaggerate\n- Never mention competitors by name\n- Keep responses under 3 sentences unless explaining value\n- If asked if you are AI, say: "I am an AI assistant from Shango Revenue Systems, and I\'m here to make sure your time is respected. Can I ask you one thing?"\n- End every call gracefully, even if rejected',
    'Initial prompt — v1 (Shango Revenue Systems / ARIA)',
    true
) ON CONFLICT (version) DO NOTHING;

-- ============================================================
-- AURORA 1.0 MIGRATIONS
-- Run these after initial schema if upgrading from Aurora 0.01
-- ============================================================

-- ADD: 9-category critique scores to calls table
ALTER TABLE calls ADD COLUMN IF NOT EXISTS pacing_score        INTEGER DEFAULT 0;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS silence_score       INTEGER DEFAULT 0;

-- ADD: Geo-routing analytics to calls table
ALTER TABLE calls ADD COLUMN IF NOT EXISTS geo_region          TEXT DEFAULT 'global';

-- ADD: Module-level diff tracking to prompt_versions
ALTER TABLE prompt_versions ADD COLUMN IF NOT EXISTS module_changes JSONB DEFAULT '[]';

-- ============================================================
-- TABLE: mars_lessons
-- Long-term MARS reflective memory — lessons survive prompt resets
-- ============================================================
CREATE TABLE IF NOT EXISTS mars_lessons (
    id              UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    lesson_type     TEXT NOT NULL CHECK (lesson_type IN (
                        'pattern', 'objection', 'opening', 'insight', 'geo', 'closing', 'discovery')),
    content         TEXT NOT NULL,           -- The actionable lesson
    source_calls    INTEGER DEFAULT 1,       -- How many calls contributed
    avg_score_delta NUMERIC(5,2) DEFAULT 0,  -- Observed/expected improvement
    mcts_reward     NUMERIC(8,4) DEFAULT 0,  -- score_delta / compute_cost
    geo_region      TEXT,                    -- Non-null if geo-specific lesson
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lessons_type    ON mars_lessons(lesson_type);
CREATE INDEX IF NOT EXISTS idx_lessons_reward  ON mars_lessons(mcts_reward DESC);
CREATE INDEX IF NOT EXISTS idx_lessons_active  ON mars_lessons(is_active);

-- RLS for mars_lessons
ALTER TABLE mars_lessons ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_all" ON mars_lessons FOR ALL USING (true);

-- ADD: Index for geo analytics
CREATE INDEX IF NOT EXISTS idx_calls_geo ON calls(geo_region);

-- ═══════════════════════════════════════════════════════════════════════════
-- AURORA 1.0 — NURTURE SEQUENCES TABLE
-- Stores AI-driven multi-step email + call sequences for lead nurturing.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS nurture_sequences (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_email      TEXT NOT NULL,
    lead_name       TEXT,
    lead_company    TEXT,
    lead_score      INTEGER DEFAULT 50,
    phone           TEXT,
    pain_points     JSONB DEFAULT '[]',
    call_summary    TEXT,
    geo_region      TEXT DEFAULT 'global',
    sequence_type   TEXT NOT NULL CHECK (sequence_type IN ('hot_nurture','warm_nurture','cold_nurture')),
    current_step    INTEGER DEFAULT 0,
    steps           JSONB NOT NULL DEFAULT '[]',
    is_active       BOOLEAN DEFAULT TRUE,
    completed       BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    last_action_at  TIMESTAMPTZ
);

ALTER TABLE nurture_sequences ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_all" ON nurture_sequences FOR ALL USING (true);

CREATE INDEX IF NOT EXISTS idx_nurture_email  ON nurture_sequences(lead_email);
CREATE INDEX IF NOT EXISTS idx_nurture_active ON nurture_sequences(is_active, completed);
CREATE INDEX IF NOT EXISTS idx_nurture_type   ON nurture_sequences(sequence_type);
