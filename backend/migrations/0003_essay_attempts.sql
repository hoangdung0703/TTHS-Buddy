-- Phase 5b: stores each essay submission (question, user's free-text answer, and the grading
-- result) per user. Used for (1) rotation logic in question_bank_service.py - avoid repeating
-- the user's most recently-served essay questions, and (2) Phase 7 weak-topics + Phase 9
-- evaluation, both of which need per-topic_category grading history. Run once manually in the
-- Supabase SQL editor, same as migrations/0001 and 0002.
create table if not exists essay_attempts (
    id uuid primary key default gen_random_uuid(),
    created_at timestamptz not null default now(),
    user_id uuid not null,
    question_id text not null,
    topic_category text,
    user_answer text not null,
    matched_points jsonb not null default '[]'::jsonb,
    missing_points jsonb not null default '[]'::jsonb,
    feedback text not null,
    suggested_dieu jsonb not null default '[]'::jsonb
);

create index if not exists essay_attempts_user_id_idx on essay_attempts (user_id, created_at desc);

-- RLS enabled for defense in depth; the backend only ever accesses this table via the
-- Supabase service role key, which bypasses RLS, so no policies are needed for the app to work.
alter table essay_attempts enable row level security;
