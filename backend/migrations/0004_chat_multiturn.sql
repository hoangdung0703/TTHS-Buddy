-- Phase 4 Extension (Query Understanding + Multi-turn): adds conversation grouping and
-- query-rewrite transparency to chat_query_logs. conversation_id is client-generated/held for
-- the lifetime of one chat session (no separate "conversations" table - grouping is purely via
-- this column on the existing log rows), letting the backend look up the last few turns of the
-- SAME conversation for query rewriting and final-answer context. rewritten_question is stored
-- alongside the original question so a bad answer can be diagnosed as "rewrite went wrong" vs
-- "retrieval went wrong" (see requirements.md Phase 4 Extension). Both columns are nullable:
-- existing rows predate this migration and never had either concept. Run once manually in the
-- Supabase SQL editor, same as migrations/0001-0003.
alter table chat_query_logs
    add column if not exists conversation_id uuid,
    add column if not exists rewritten_question text;

create index if not exists chat_query_logs_conversation_id_idx on chat_query_logs (conversation_id, created_at desc);

-- RLS is already enabled on chat_query_logs (migration 0001); no policy changes needed since
-- the backend only ever accesses this table via the Supabase service role key.
