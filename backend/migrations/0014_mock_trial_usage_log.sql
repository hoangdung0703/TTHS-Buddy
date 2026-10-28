-- Feature "Phiên tòa giả định": usage log for the daily case limits (docs/phien-toa-gia-dinh/THIET-KE.md
-- Mục 11.10, chặng R1b). Requires nothing but auth.users. Run once manually in the Supabase SQL editor,
-- same as 0001-0013. NOT run by any script. MUST be run before TRIAL_ENABLED is turned on: the backend
-- refuses to create a case (503 trial_usage_log_unavailable) while this table cannot be read.
--
-- Why: the limits (5 cases/day/user, TRIAL_GLOBAL_DAILY_CASE_LIMIT for everyone) used to count rows
-- of mock_trial_cases, and deleting a session hard-deletes its case, so deleting freed the quota.
-- One row here per SUCCESSFUL case creation; it is never deleted with the session or the case.
-- Rows hold only who and when - never any case content or utterance. The backend deletes rows older
-- than 35 days opportunistically when it writes a new one (no cron).
--
-- Additive only: a new table and its indexes; no existing table or row is touched. Idempotent.

begin;

create table if not exists mock_trial_usage_log (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    created_at timestamptz not null default now()
);

-- Global daily cap (count since the start of the Vietnam day) and the 35-day cleanup.
create index if not exists mock_trial_usage_log_created_idx on mock_trial_usage_log (created_at);
-- Per-user daily limit.
create index if not exists mock_trial_usage_log_user_created_idx on mock_trial_usage_log (user_id, created_at);

-- Same posture as 0012: RLS on and no policy, so the anon/authenticated roles cannot read or write
-- this table at all; only the backend (service role) does.
alter table mock_trial_usage_log enable row level security;

commit;

-- Check after running (read-only):
--   select count(*) from mock_trial_usage_log;
--   select indexname from pg_indexes where tablename = 'mock_trial_usage_log';
