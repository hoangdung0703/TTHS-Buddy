-- Feature nho - Xoa/doi ten hoi thoai + Sao chep cau tra loi (see requirements.md). Adds an
-- optional custom title, set via PATCH /api/chat/conversations/{conversation_id} and denormalized
-- onto every chat_query_logs row sharing that conversation_id (there is no separate
-- "conversations" table - grouping/title live entirely on the log rows, same as conversation_id
-- itself per migrations/0004). Nullable: null means "no custom title yet", in which case
-- list_conversations falls back to the truncated first question exactly as before this migration.
-- Run once manually in the Supabase SQL editor, same as migrations/0001-0004.
alter table chat_query_logs
    add column if not exists title text;

-- RLS is already enabled on chat_query_logs (migration 0001); no policy changes needed since
-- the backend only ever accesses this table via the Supabase service role key.
