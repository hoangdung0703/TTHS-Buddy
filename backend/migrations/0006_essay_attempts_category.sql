-- Phase 5a/5b v2 Buoc B: adds the "category" column (ban_trac_nghiem/ly_thuyet/van_dung/
-- tinh_huong - see ingestion/question_bank.json's new "category" field) to essay_attempts, so
-- per-bank practiced-question counts (Dashboard Khoi 2, /essay bank cards) can be queried
-- directly instead of joining back to question_bank.json by question_id at read time (fragile
-- once question_id values rotate/change across re-parses). topic_category is untouched - still
-- the old free-text field used by Phase 7 weak-topics, a different concept from the new bank
-- category. Run once manually in the Supabase SQL editor, same as migrations/0001-0005.
alter table essay_attempts add column if not exists category text;

create index if not exists essay_attempts_user_category_idx on essay_attempts (user_id, category);
