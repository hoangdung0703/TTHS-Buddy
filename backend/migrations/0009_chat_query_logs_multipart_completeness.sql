-- requirements.md "Viec 3" Buoc 3 completeness guard: logs which 1-indexed PHAN numbers (of the
-- sub_questions sent to rag_service.py's multi-part branch), if any, never appeared in the
-- generated answer before it was sent to the client - discovered when the multi-part path's
-- fallback model (see gemini_client.stream_generate_answer's fallback_model docstring) was
-- observed silently dropping the first N-2 of 5 PHAN despite each PHAN having correct, isolated
-- retrieved context. A fail-closed guard (unlike rule9_ungrounded_dieu_numbers's plain-streamed
-- path, which is log-only) - see rag_service.py's _multipart_missing_parts docstring. Null means
-- this branch never ran the check (not a multi-part answer at all); [] means it ran and every
-- PHAN was present. Run once manually in the Supabase SQL editor, same as migrations/0001-0008.
alter table chat_query_logs
    add column if not exists multipart_missing_parts jsonb;

-- Same rationale as migrations/0008's rule9_ungrounded_dieu_numbers index - cheap lookup of every
-- row with a real completeness violation for continuous monitoring, without scanning the whole
-- table (the common case, '[]'::jsonb or null, needs no index scan).
create index if not exists chat_query_logs_multipart_incomplete_idx on chat_query_logs (created_at)
    where multipart_missing_parts is not null and multipart_missing_parts != '[]'::jsonb;
