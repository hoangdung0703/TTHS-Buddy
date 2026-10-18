-- Vở ghi Giai đoạn 2 ("Hỏi AI trên đoạn được chọn"): records which surface a chat_query_logs row
-- came from. 'chat' = the Chat page (every row written before this migration, hence the default);
-- 'notes' = POST /api/notes/ask. The Chat sidebar/history reads filter on source = 'chat' so a
-- question asked inside Vở ghi never shows up as a Chat conversation.
--
-- The selected passage itself is NEVER stored - not in this table, not anywhere. A 'notes' row
-- carries the same question/answer/citation fields as a chat row; the passage's length lives only
-- in the request telemetry log line.
--
-- Idempotent (add column if not exists): safe to run twice. Adding a column with a constant
-- default is a metadata-only change on Postgres 11+, so existing rows are not rewritten. Run once
-- manually in the Supabase SQL editor, same as migrations/0001-0010. The backend tolerates this
-- column being absent (see chat_log_service) so deploying code before running this cannot break
-- the existing Chat.
alter table chat_query_logs
    add column if not exists source text not null default 'chat';
