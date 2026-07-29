-- Phase 4: logs every /api/chat/query call for later evaluation (Phase 9 - citation accuracy,
-- groundedness, correct-refusal rate). Run once manually in the Supabase SQL editor; this
-- project has no migration runner/ORM (per requirements.md tech stack), so schema changes are
-- applied by hand the same way the Qdrant collection is bootstrapped in code but the Postgres
-- schema is not.
create table if not exists chat_query_logs (
    id uuid primary key default gen_random_uuid(),
    created_at timestamptz not null default now(),
    user_id uuid not null,
    question text not null,
    answer text not null,
    is_fallback boolean not null,
    used_academic_reference boolean not null,
    citations jsonb not null default '[]'::jsonb,
    related_articles jsonb not null default '[]'::jsonb,
    retrieved_chunks jsonb not null default '[]'::jsonb
);

create index if not exists chat_query_logs_user_id_idx on chat_query_logs (user_id);
create index if not exists chat_query_logs_created_at_idx on chat_query_logs (created_at);

-- RLS enabled for defense in depth; the backend only ever accesses this table via the
-- Supabase service role key, which bypasses RLS, so no policies are needed for the app to work.
alter table chat_query_logs enable row level security;
