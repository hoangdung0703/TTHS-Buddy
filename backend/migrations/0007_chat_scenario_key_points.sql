-- "Sinh tình huống minh họa" feature (see requirements.md), Lượt 1: adds the hidden key_points
-- rubric column for intent=request_scenario rows. Never read back by the public API - only
-- chat_log_service.log_chat_query writes it, and only a future Lượt 2 (answer_evaluation grading,
-- not built yet) will read it back. Nullable: every other intent's row (and every row logged
-- before this migration) has no rubric at all. Run once manually in the Supabase SQL editor, same
-- as migrations/0001-0006.
alter table chat_query_logs
    add column if not exists scenario_key_points jsonb;
