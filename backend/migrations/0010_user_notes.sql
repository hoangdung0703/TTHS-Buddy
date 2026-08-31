-- Feature "Vở ghi cá nhân" (requirements.md "Feature - Vở ghi cá nhân + Chat trả lời dựa trên
-- nội dung ghi chú") - THIS MIGRATION IS FOUNDATION ONLY (storage + CRUD). The Chat/retrieval
-- integration described in that section is a separate, later step and does not touch this table
-- beyond reading it. Run once manually in the Supabase SQL editor, same as migrations/0001-0009.
create table if not exists user_notes (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    title text,
    content text not null,
    tag text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists user_notes_user_id_idx on user_notes (user_id, updated_at desc);

-- RLS enabled for defense in depth; the backend only ever accesses this table via the Supabase
-- service role key, which bypasses RLS, so no policies are needed for the app to work. This is
-- the same posture as essay_attempts/quiz_attempts (see 0002/0003) - here it matters MORE, since
-- notes are free-text content the user wrote themselves, not system-generated grading history.
alter table user_notes enable row level security;
