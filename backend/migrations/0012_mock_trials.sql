-- Feature "Phiên tòa giả định" (docs/phien-toa-gia-dinh/THIET-KE.md, decisions of 2026-10-19).
-- Run once manually in the Supabase SQL editor, same as 0001-0011. NOT run by any script.
--
-- Three tables: a generated case (immutable after validation), a session that plays the case in
-- one user role, and the session's utterances (source of the final biên bản). Step order is
-- enforced by the backend state machine (app/services/trial_state_machine.py); the CHECK
-- constraints below are a second line only.
--
-- Limits (5 cases/day/user, at most 3 active sessions, auto-abandon after 14 days) are enforced by
-- the backend using the indexes below; there is no trigger or cron here. Deleting a session is a
-- hard delete of its case row: the cascades remove the session and every utterance with it.

create table if not exists mock_trial_cases (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    created_at timestamptz not null default now(),
    -- Key into the crime whitelist in app/services/trial_config.py, e.g. 'blhs_173'.
    crime_key text not null,
    case_schema_version smallint not null,
    -- Validated CaseFile (Pydantic, extra="forbid"). Never edited after insert.
    case_json jsonb not null,
    -- sha256 of case_json as stored; lets every turn confirm it works on the same case.
    case_hash text not null,
    -- Deterministic legal pack: [{source_document, dieu_number}] fetched by key at creation.
    -- Rule 9 for this case is checked against exactly this list.
    legal_pack jsonb not null,
    generation_model text not null,
    generation_attempts smallint not null default 1
);

-- Daily case limit: count rows for (user_id, created_at >= today).
create index if not exists mock_trial_cases_user_created_idx on mock_trial_cases (user_id, created_at desc);

create table if not exists mock_trial_sessions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    case_id uuid not null references mock_trial_cases (id) on delete cascade,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    completed_at timestamptz,
    -- Phase 1 enables 'ksv' and 'luat_su' only; the other values are accepted here so later roles
    -- need no migration, and rejected by the API until enabled.
    user_role text not null check (user_role in ('chu_toa', 'thu_ky', 'ksv', 'luat_su', 'bi_cao')),
    current_step smallint not null default 1 check (current_step between 1 and 11),
    slot_index smallint not null default 0 check (slot_index >= 0),
    slot_user_turns smallint not null default 0 check (slot_user_turns >= 0),
    pending_ai boolean not null default true,
    status text not null default 'active' check (status in ('active', 'completed', 'abandoned')),
    -- Optimistic concurrency: every write is "update ... where id = $1 and version = $expected";
    -- 0 rows updated -> HTTP 409 with the current state.
    version integer not null default 0,
    -- Generation lock: set to now() + budget before an AI turn, cleared after. A stale value
    -- (crashed worker) simply expires. Prevents two concurrent AI turns for one session.
    generating_until timestamptz,
    -- Append-only minor details the AI characters added during the hearing.
    fact_ledger jsonb not null default '[]'::jsonb,
    -- Structured nghị án decision; never sent to the client.
    verdict_json jsonb,
    verdict_flags jsonb not null default '[]'::jsonb,
    constraint mock_trial_sessions_completed_chk check ((status = 'completed') = (completed_at is not null))
);

-- Active-session limit and the session list.
create index if not exists mock_trial_sessions_user_status_idx on mock_trial_sessions (user_id, status, updated_at desc);
-- Auto-abandon sweep: status = 'active' and updated_at < now() - interval '14 days'.
create index if not exists mock_trial_sessions_status_updated_idx on mock_trial_sessions (status, updated_at);

create table if not exists mock_trial_utterances (
    id bigint generated always as identity primary key,
    session_id uuid not null references mock_trial_sessions (id) on delete cascade,
    user_id uuid not null,
    created_at timestamptz not null default now(),
    seq integer not null,
    step smallint not null check (step between 1 and 11),
    -- Participant id: CHU_TOA, HOI_THAM_1, HOI_THAM_2, THU_KY, KSV, LUAT_SU, BI_CAO, BI_HAI,
    -- NLC_1, NLC_2, NLQ. Names live in the case's participants map, not here.
    speaker_id text not null,
    is_user boolean not null,
    -- 'notice' = order-keeping reminders (e.g. refusing to skip a step); excluded from the biên bản.
    kind text not null default 'speech' check (kind in ('speech', 'procedural', 'notice')),
    addressee text,
    content text not null check (char_length(content) <= 8000),
    guard_flags jsonb not null default '[]'::jsonb,
    unique (session_id, seq)
);

-- RLS enabled for defense in depth, with NO policies - the same posture as 0002/0003/0010: the
-- backend only ever accesses these tables with the service-role key (which bypasses RLS) and
-- always filters by user_id itself. With RLS on and no policy, the anon/authenticated roles can
-- read or write nothing here, which also keeps clients from bypassing the step-order rules.
alter table mock_trial_cases enable row level security;
alter table mock_trial_sessions enable row level security;
alter table mock_trial_utterances enable row level security;
