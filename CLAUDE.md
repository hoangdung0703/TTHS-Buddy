# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

TTHS Buddy is a study assistant for Vietnamese Criminal Procedure Law (BLTTHS): citation-grounded RAG chat, MCQ quiz, dashboard, personal notes, and a mock-trial module ("Phiên tòa giả định"). Next.js 15 / React 19 frontend (`frontend/`), FastAPI backend (`backend/`), Supabase (Postgres + Auth), Qdrant (vectors), Gemini (embeddings + generation). `README.md` covers setup, env vars and the API table; this file covers what isn't obvious from it.

## Commands

Backend (run from `backend/`, venv at `backend/.venv`):
```
uvicorn app.main:app --reload                               # dev server; startup checks Supabase + Qdrant
python -m unittest discover -s tests -t tests               # all unit tests (stdlib unittest, no pytest)
python -m unittest tests.test_trial_state_machine           # one module
python -m unittest tests.test_trial_state_machine.SomeClass.test_x   # one test
```
`backend/tests/` makes no network calls. Tests that need real statute text read the gitignored `ingestion/chunks.json` and skip when it is missing.

`backend/evaluation/*.py` (including the `test_*.py` there) are **not** unit tests. They hit a live backend / real Gemini (e.g. `run_evaluation.py`, the 29-question eval; `run_trial_*_e2e.py`) and cost Gemini credit. See the budget rule below.

Frontend (run from `frontend/`):
```
npm run dev            # http://localhost:3000; mock data (lib/mockData.ts) unless NEXT_PUBLIC_USE_MOCK_DATA is exactly "false" (unset = mock on)
npx tsc --noEmit       # type check (no npm script for it)
npm run build
npm run lint
npm test               # node --test tests/*.test.mjs (pure-logic tests for lib/trial*.ts)
node --test tests/trialRules.test.mjs
```
Browser e2e (Playwright, not in package.json; backend and Supabase are faked, no credentials needed). See `frontend/tests/e2e/README.md`:
```
tests/e2e/build.sh && node tests/e2e/suite.mjs
```
`build.sh` builds a copy in `$TMPDIR/ttths-e2e` and serves it on port 3011, so it never touches `frontend/.next` or `.env*`.

Ingestion (run from repo root, manual only; never run by the app):
```
python -m ingestion.parse_law --all            # PDFs in ingestion/raw_documents -> ingestion/chunks.json
python -m ingestion.parse_law --file "<x>.pdf"
python -m ingestion.embed_and_upsert           # idempotent, deterministic point IDs
python -m ingestion.test_chuong_muc            # most ingestion checks are runnable modules, not unittest
python -m unittest ingestion.test_registry_templates   # the exception: a unittest (form templates never reach the index)
```

Migrations: plain SQL in `backend/migrations/NNNN_*.sql`, applied by hand in the Supabase SQL editor, in order. There is no runner. New tables get RLS enabled with no policies (the backend uses the service-role key). Code that reads or writes a table must still work if the migration hasn't been applied yet (log and continue).

## Gemini budget rule

Real Gemini calls are scarce, and the key may be shared with production. Before any batch of live calls (eval scripts, e2e trial runs, repeated generation tests), estimate the call and token count. Over ~300 calls, ask the user first. On 402/429, stop immediately: no retry loop. For tests that only measure generation variance, cache retrieval once and repeat only the generation.

## Architecture

### Backend layout
`app/api/*` routers: auth (`require_supabase_user`, Supabase JWT via JWKS), `@limiter.limit` (slowapi), SSE framing. `app/services/*` hold the logic. `app/prompts/*` hold every LLM prompt. `app/models/*` are Pydantic schemas. `app/core/` has settings (`config.py`, pydantic-settings, env aliases), data access, rate limits, middleware, and request telemetry. `main.py` builds clients in `lifespan` and stores them on `app.state`.

Streaming routes follow one pattern, and new routes reuse it: auth and rate limit run outside the SSE generator, and all I/O runs inside it. `CancelledError` is logged as the outcome `cancelled`. Other errors emit an `error` event and close cleanly. Ownership failures return 404, not 403. Telemetry records lengths and counts, never the text a user wrote.

### RAG chat (`services/rag_service.py`, `query_understanding_service.py`, `api/chat.py`)
Query understanding (rewrite, scope check, sub-question split, anonymisation) → retrieval → generation → guards → `chat_log_service`. Retrieval mixes an exact Điều lookup (`detect_dieu_number` / `detect_source_document`), HyDE-embedded semantic search, and an LLM re-rank over `legal_text` chunks, plus `academic_reference` chunks with neighbour expansion. Aggregate-structure questions ("how many chapters…") and repealed Điều are answered deterministically from Qdrant payloads.

**Rule 9** is the core invariant: an answer may only cite Điều numbers that retrieval returned in `legal_primary`. The prompt alone does not enforce it (measured), so `_rule9_ungrounded_dieu_numbers` runs in code. Answers that used `academic_reference`, and every multi-part answer, are buffered instead of token-streamed. A violation replaces the whole answer with a fixed fallback; the code never patches individual spots. Ordinary single answers stream and only log a Rule 9 miss. The HyDE disable switch is honoured only outside production.

### Mock trial (`services/trial_*.py`, `api/trials.py`, `docs/phien-toa-gia-dinh/`)
Gated by `TRIAL_ENABLED` (off means every `/api/trials*` route returns 404) and optionally by `TRIAL_ALLOWED_EMAILS`. There is a per-user and a global daily case quota (`trial_usage_log`).

- `trial_state_machine.py` is a pure, deterministic 11-step hearing. Each step is a list of slots (role, kind `speech`/`qa_loop`/`long_speech`, end conditions). A slot whose role equals the user's role is the user's turn; every other slot is an AI turn. **The LLM can never change state.** Every write carries `expected_step` + `expected_version`, and any mismatch or disallowed action is a 409. Skip requests made in words are caught by a keyword detector before any LLM call.
- User roles: KSV, Người xem (observer), Thư ký (`trial_clerk.py`), Bị cáo (`trial_defendant.py`), Chủ tọa (`trial_presiding.py` for steps 2–9, `trial_chair_decision.py` for deliberation and the structured decision). Adding a role adds slot behaviour and UI, not a new engine.
- One LLM call generates a run of AI utterances, with the speaker enum restricted per slot via the response schema. Legally weighty long speeches (indictment, defence, judgment) get one call each. Everything is buffered and passed through guards before it is sent or saved: role/fact guards, Rule 9 by (Điều, statute) pair in `trial_rule9.py`, and the verdict guard in `trial_verdict_guard.py`. A half-generated segment is never persisted.
- The case file is JSON validated by Pydantic (`extra="forbid"`, `trial_case_validator.py`). The legal pack is built from real chunks (`trial_legal_pack.py`). The record follows form Mẫu 22-HS (`trial_record*.py`).
- `docs/phien-toa-gia-dinh/THIET-KE.md` is the design doc. Dated "Quyết định" sections override the body text where they conflict. `API-CONTRACT.md` is the frontend/backend contract that the e2e fakes (`tests/e2e/*.mjs`) mirror. Change both sides together.

### Frontend
App Router pages in `src/app/*`. All backend calls go through `src/lib/api.ts`. The Supabase session comes from `useAuthSession`. Trial UI lives in `src/components/trial/*`. Pure trial logic sits in `src/lib/trial*.ts`, which is the part the `node --test` suite covers. The UI renders only the `allowed_actions` the server returns, never a client-side guess. `NEXT_PUBLIC_*` vars must be in `frontend/.env.local`, not the root `.env`. `frontend.md` has the design-system notes. The app is a PWA (`public/sw.js`).

## Conventions

- UI text, prompts, design docs and many code comments are in Vietnamese. Keep legal terms (Điều, khoản, điểm, BLHS, BLTTHS) as they are.
- `requirements.md` is the phase-by-phase spec and build log. Long-form rationale goes there or in the trial design doc, not in commit messages.
- Commit style: Conventional Commits with scopes such as `feat(trial)`, `feat(trial-ui)`, `fix(ui)`, `test(e2e)`.
- `ingestion/raw_documents/` and `ingestion/chunks*.json` are gitignored (copyrighted PDFs and derived text). Never commit them. `ingestion/question_bank.json` is committed and edited by hand (see `question_bank.TEMPLATE.md`). The repo must not go public until the history rewrite described in README is done.
- Deployment: frontend on Vercel, backend on Render (`render.yaml`, `DEPLOYMENT.md`). A GitHub Action pings Supabase every 3 days to keep the free tier awake.
