-- Phase 5a: stores each quiz attempt (which questions were shown, the user's answers, and the
-- score) per user. Used for (1) rotation logic in question_bank_service.py - avoid repeating
-- the questions shown in the user's most recent attempt at the same quiz_set, and (2) Phase 7
-- weak-topics, which needs per-topic_category correctness across attempts. Run once manually
-- in the Supabase SQL editor, same as migrations/0001_chat_query_logs.sql.
create table if not exists quiz_attempts (
    id uuid primary key default gen_random_uuid(),
    created_at timestamptz not null default now(),
    user_id uuid not null,
    quiz_set integer not null,
    question_ids jsonb not null,
    answers jsonb not null,
    score integer not null,
    total integer not null
);

create index if not exists quiz_attempts_user_quiz_set_idx on quiz_attempts (user_id, quiz_set, created_at desc);

-- RLS enabled for defense in depth; the backend only ever accesses this table via the
-- Supabase service role key, which bypasses RLS, so no policies are needed for the app to work.
alter table quiz_attempts enable row level security;
