-- RAG_SYSTEM_PROMPT rule 9 grounding audit (see requirements.md investigation): logs which Dieu
-- numbers, if any, the model wrote in a legal_question answer without them being grounded in any
-- retrieved legal_text chunk (a rule 9 violation - e.g. citing a Dieu number that only appeared
-- inside an academic_reference chunk's own text). Log-only, not a fail-closed guard - see
-- rag_service.py's _rule9_ungrounded_dieu_numbers docstring for why. Null/empty array means the
-- check ran and found nothing (or the branch doesn't generate a legal-content answer at all, e.g.
-- greeting); every row logged before this migration has no value at all. Run once manually in the
-- Supabase SQL editor, same as migrations/0001-0007.
alter table chat_query_logs
    add column if not exists rule9_ungrounded_dieu_numbers jsonb;

-- For continuous monitoring (requirements.md ask: "dữ liệu giám sát liên tục, không chỉ dựa vào
-- lần eval test") - lets a dashboard/query cheaply find every row with a real violation without
-- scanning the whole table, since jsonb '[]'::jsonb (the common case) doesn't need an index scan
-- avoided but a non-empty array does benefit from one.
create index if not exists chat_query_logs_rule9_violations_idx on chat_query_logs (created_at)
    where rule9_ungrounded_dieu_numbers is not null and rule9_ungrounded_dieu_numbers != '[]'::jsonb;
