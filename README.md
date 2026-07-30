# TTHS Buddy

TTHS Buddy is an AI study assistant for Vietnamese Criminal Procedure Law (Bộ luật Tố tụng
Hình sự), built as an NCKH (student research) project. It answers student questions with
citation-grounded RAG over the actual statute text (not the model's internal knowledge),
and includes a quiz module, an essay-grading module, and a personal study dashboard.

Stack: Next.js (TypeScript) frontend, FastAPI (Python) backend, Supabase (Postgres + Auth),
Qdrant Cloud (vector search), Gemini (embeddings + generation).

## Project structure

```
frontend/          Next.js app (App Router), Tailwind, Supabase Auth client
backend/           FastAPI app
  app/api/         Route handlers (chat, quiz, essay, dashboard, health)
  app/services/     Business logic (RAG, quiz grading, essay grading, dashboard aggregation)
  app/models/       Pydantic request/response models
  app/core/         Settings, Supabase/Qdrant client setup, JWT auth, logging
  migrations/       Hand-written SQL, run manually in the Supabase SQL editor (no ORM/migration
                    runner - see "Database migrations" below)
  evaluation/       Phase 9 evaluation: fixed test set + script measuring citation accuracy,
                    groundedness, correct-refusal rate
ingestion/          Standalone CLI pipeline: PDF -> chunks.json -> Qdrant, and the question-bank
                    parser. Run by hand whenever source documents change (not part of app startup)
requirements.md     Full project spec, phase-by-phase build log, and Definition of Done per phase
frontend.md         Frontend design notes (design system, scope trade-offs vs the Figma mockups)
```

## Requirements

- Node.js 20+
- Python 3.11+
- A Supabase project (Auth + Postgres)
- A Qdrant Cloud cluster (or self-hosted Qdrant)
- A Google AI Studio API key (Gemini)

## Setup

1. Copy `.env.example` to `.env` at the repository root and fill in the backend/ingestion
   values (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `GOOGLE_API_KEY`,
   `GEMINI_CHAT_MODEL`, `GEMINI_EMBEDDING_MODEL`, `QDRANT_URL`, `QDRANT_API_KEY`,
   `QDRANT_COLLECTION`).
2. Copy the frontend section of `.env.example` into `frontend/.env.local`
   (`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_BASE_URL`,
   `NEXT_PUBLIC_USE_MOCK_DATA`). Next.js only reads `NEXT_PUBLIC_*` vars from its own package
   directory, not the root `.env`.
3. Install backend dependencies: `pip install -r backend/requirements.txt` (a virtualenv is
   recommended - the repo's own `.venv/` is gitignored).
4. Install frontend dependencies: `npm install` from `frontend/`.
5. Run the database migrations (see below) once against your Supabase project.
6. Run the ingestion pipeline (see below) once to populate Qdrant, or point at an already-
   populated collection.

## Running the app

Backend (from `backend/`):
```
uvicorn app.main:app --reload
```
On startup it verifies the Supabase connection, ensures the Qdrant collection and its payload
indexes exist, and logs both. `GET /api/health` returns `{"status": "ok"}` once ready.

Frontend (from `frontend/`):
```
npm run dev
```
Serves at `http://localhost:3000`. Set `NEXT_PUBLIC_USE_MOCK_DATA=false` in
`frontend/.env.local` to call the real backend instead of the built-in mock data (`lib/mockData.ts`).

## Database migrations

This project has no ORM/migration runner - schema changes are plain `.sql` files under
`backend/migrations/`, applied by hand in the Supabase SQL editor, once, in order:

```
0001_chat_query_logs.sql   Phase 4 - logs every chat query for Phase 9 evaluation
0002_quiz_attempts.sql     Phase 5a - quiz submissions, feeds rotation + dashboard weak-topics
0003_essay_attempts.sql    Phase 5b - essay submissions, same purpose for the essay module
```
All three tables have RLS enabled but no policies - the backend only ever accesses them via the
Supabase service-role key, which bypasses RLS. Reads/writes degrade gracefully (log + continue)
if a table doesn't exist yet, so the app still runs before migrations are applied - quiz/essay
rotation and dashboard stats just report no history until the tables exist.

## Running ingestion

The ingestion pipeline is a manual CLI step, re-run only when source documents change - it is
never triggered automatically by the app. Source PDFs live in `ingestion/raw_documents/` (not
committed - see `.gitignore`) and are listed in `ingestion/document_registry.py`.

1. **Parse PDFs into chunks** (`ingestion/chunks.json`, also gitignored):
   ```
   python -m ingestion.parse_law --all
   ```
   Dispatches each document to the `legal_text` or `academic_reference` chunking strategy per
   `document_registry.py`, with an OCR fallback (Gemini Vision, then Tesseract) for pages the
   primary PDF text layer can't extract cleanly. Use `--file "<name>.pdf"` to test a single
   document instead of the full batch.

2. **Embed and upsert into Qdrant**:
   ```
   python -m ingestion.embed_and_upsert
   ```
   Idempotent - point IDs are deterministic (derived from `source_type` + `dieu_number`/
   `chunk_index` + `law_version`), so re-running after `chunks.json` changes overwrites the same
   points instead of duplicating them. Also ensures the 3 payload indexes the backend filters on
   (`source_type`, `dieu_number`, `source_document`) exist.

3. **Parse the question bank** (`ingestion/question_bank.json`, committed - law-student-authored
   content, not third-party copyrighted like the PDFs above):
   ```
   python -m ingestion.parse_question_bank
   ```
   Parses `Câu hỏi trắc nghiệm.pdf` (MCQ) and `Tôi hỏi bạn trả lời.pdf` (Đúng/Sai + essay) into
   the unified schema used by the quiz and essay modules. Prints a full review dump - spot-check
   before trusting a fresh run, per the Phase 5a methodology in `requirements.md`.

## Phase 9 evaluation

`backend/evaluation/test_set.json` is a fixed 29-question set (direct citation, analytical, and
out-of-scope categories) with hand-verified ground truth against the ingested corpus. Run it
against a live backend:

```
export EVAL_USER_EMAIL=your_test_account_email
export EVAL_USER_PASSWORD=your_test_account_password
python backend/evaluation/run_evaluation.py
```

The account must already exist in Supabase Auth (sign up via `/register`, or create it in the
Supabase dashboard) - the script only signs in. It calls the real `POST /api/chat/query` for
every question, computes citation accuracy / groundedness / correct-refusal rate, prints a report,
and writes full per-question detail to `backend/evaluation/results.json`.

## API reference

All routes except `/api/health` require a Supabase JWT (`Authorization: Bearer <token>`); an
invalid/missing token returns 401.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness check, `{"status": "ok"}` |
| GET | `/api/chat/suggestions` | Static cold-start question chips |
| POST | `/api/chat/query` | Ask a question; grounded RAG answer + citations + follow-up chips |
| GET | `/api/quiz/sets` | List the 5 MCQ quiz sets |
| POST | `/api/quiz/generate` | Get a rotation-selected batch of questions for a quiz set |
| POST | `/api/quiz/submit` | Grade MCQ answers, persist the attempt |
| POST | `/api/essay/question` | Get a rotation-selected essay question |
| POST | `/api/essay/submit` | LLM-as-judge grading against the question's rubric, persist the attempt |
| GET | `/api/dashboard/keywords-yesterday` | Điều asked about yesterday (VN time), grouped + counted |
| GET | `/api/dashboard/weak-topics` | Topics scoring under 50% across quiz + essay attempts |
| GET | `/api/dashboard/stats` | `{total_quiz_attempts, average_score, dieu_studied_count}` |

See `requirements.md` for full request/response shapes and the design rationale behind each route.
