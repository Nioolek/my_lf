-- Migration 003: Add missing columns for langgraph_api compatibility

-- Add enabled column to crons
ALTER TABLE crons ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT true;

-- Add end_time column to crons
ALTER TABLE crons ADD COLUMN IF NOT EXISTS end_time TIMESTAMPTZ;

-- Add timezone column to crons
ALTER TABLE crons ADD COLUMN IF NOT EXISTS timezone TEXT;

-- Add on_run_completed column to crons
ALTER TABLE crons ADD COLUMN IF NOT EXISTS on_run_completed TEXT;

-- Add version column to assistants
ALTER TABLE assistants ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

-- Add expires_at column to threads (for TTL support)
ALTER TABLE threads ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

-- Add assistant_id column to threads (for cascade delete)
ALTER TABLE threads ADD COLUMN IF NOT EXISTS assistant_id UUID REFERENCES assistants(assistant_id) ON DELETE SET NULL;

-- Add user_id column to runs
ALTER TABLE runs ADD COLUMN IF NOT EXISTS user_id TEXT;

-- Add attempt column to runs
ALTER TABLE runs ADD COLUMN IF NOT EXISTS attempt INTEGER NOT NULL DEFAULT 1;