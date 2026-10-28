-- Feature "Phiên tòa giả định": the remaining user roles (docs/phien-toa-gia-dinh/THIET-KE.md
-- Mục 11, decisions of 2026-10-29). Requires 0012. Run once manually in the Supabase SQL editor,
-- same as 0001-0012. NOT run by any script.
--
-- Widening only; no row is read, rewritten or deleted:
-- - user_role also accepts 'nguoi_xem' (Người xem). 0012 declared the check inline, so Postgres
--   named it itself; every CHECK on mock_trial_sessions that mentions user_role is dropped and
--   one named check is added back with the wider list. The new list is a superset of the old one,
--   so every existing row satisfies it.
-- - mock_trial_utterances.procedure_item: the procedural item a Chủ tọa utterance performs.
-- - mock_trial_sessions.user_work: the student's work that is not an utterance (Thư ký notes and
--   record draft, Chủ tọa draft decision). Never put into a prompt.
-- Both columns are nullable without a default: a metadata-only change, existing rows untouched.
--
-- Idempotent: safe to run twice. The API keeps rejecting a role until its stage enables it
-- (config.user_roles), so running this before deploying code changes no behaviour.

begin;

do $$
declare
    con record;
begin
    for con in
        select c.conname
        from pg_constraint c
        where c.conrelid = 'public.mock_trial_sessions'::regclass
          and c.contype = 'c'
          and pg_get_constraintdef(c.oid) like '%user_role%'
    loop
        execute format('alter table public.mock_trial_sessions drop constraint %I', con.conname);
    end loop;
end $$;

-- NOT VALID then VALIDATE: the add takes only a brief lock; validation scans without blocking writes.
alter table public.mock_trial_sessions
    add constraint mock_trial_sessions_user_role_chk
    check (user_role in ('chu_toa', 'thu_ky', 'ksv', 'luat_su', 'bi_cao', 'nguoi_xem')) not valid;
alter table public.mock_trial_sessions validate constraint mock_trial_sessions_user_role_chk;

alter table public.mock_trial_utterances
    add column if not exists procedure_item text;

alter table public.mock_trial_sessions
    add column if not exists user_work jsonb;

commit;

-- Check after running (read-only):
--   select conname, pg_get_constraintdef(oid) from pg_constraint
--   where conrelid = 'public.mock_trial_sessions'::regclass and contype = 'c';
--   select table_name, column_name from information_schema.columns
--   where table_name in ('mock_trial_sessions', 'mock_trial_utterances')
--     and column_name in ('procedure_item', 'user_work');
