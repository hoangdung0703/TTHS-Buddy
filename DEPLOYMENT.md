# Deployment guide — Vercel (frontend) + Render (backend)

Manual setup via each dashboard. Nothing in this doc auto-deploys; it's a checklist plus the
files in this repo that make the dashboard steps line up.

## Backend — Render

**Runtime: native Python (no Docker).** `backend/requirements.txt` is a standard pip
requirements file, so Render auto-detects the Python environment — no Dockerfile needed.
`gunicorn` has been added to `backend/requirements.txt` for the production start command.

You can either click through the Dashboard by hand, or use the included `render.yaml`
("New +" → "Blueprint", point it at this repo) which pre-fills the settings below and prompts
you for the secret values.

### Dashboard settings (if creating the service by hand)

| Setting | Value |
|---|---|
| Runtime | Python 3 |
| Root Directory | *(leave blank — repo root, NOT `backend/`)* |
| Build Command | `pip install -r backend/requirements.txt` |
| Start Command | `gunicorn -k uvicorn.workers.UvicornWorker -w 2 --bind 0.0.0.0:$PORT --chdir backend app.main:app` |
| Health Check Path | `/api/health` |

**Why Root Directory must stay at repo root:** `backend/app/core/config.py` resolves
`PROJECT_ROOT` three directories up from itself and reads
`ingestion/question_bank.json` + `ingestion/chat_suggestions_seed.json` at startup (quiz/chat
suggestions data). Those files live next to `backend/`, not inside it — if Render's root
directory were set to `backend/`, the repo checkout would still include `ingestion/`, but keep
Root Directory unset/`.` to avoid any ambiguity.

**Why `-w 2` (not the usual `2×CPU+1`):** Render's free/Starter tier caps RAM at 512MB. More
workers than that would risk the OOM killer under load. This is the exact recommendation
recorded in `requirements.md`'s capacity audit, following the earlier fix that moved blocking
Gemini calls onto `asyncio.to_thread` (10-concurrent TTFB improved from 25.89s → 5.56s before
Gunicorn even enters the picture — the worker count is a separate, complementary win for
fault isolation and multi-core use).

### Environment variables to set on Render

All of these are read from `os.environ` via `pydantic-settings` in
`backend/app/core/config.py` — nothing is hardcoded, so filling these in on the Dashboard is
the only step needed.

| Variable | Notes |
|---|---|
| `ENVIRONMENT` | Set to `production` |
| `SUPABASE_URL` | From Supabase project settings |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key — **secret**, never expose to frontend |
| `SUPABASE_JWT_SECRET` | Kept for compatibility; JWT verification actually uses JWKS (ES256) |
| `GOOGLE_API_KEY` | Gemini API key — **secret** |
| `GEMINI_CHAT_MODEL` | e.g. `gemini-3.1-flash-lite` |
| `GEMINI_EMBEDDING_MODEL` | e.g. `gemini-embedding-001` |
| `QDRANT_URL` | Qdrant Cloud cluster URL |
| `QDRANT_API_KEY` | Qdrant Cloud API key — **secret** |
| `QDRANT_COLLECTION` | e.g. `ttths_law_chunks` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated. Must include the real Vercel URL (e.g. `https://ttths-buddy.vercel.app`) once it exists — defaults to `http://localhost:3000` if unset, which will block the deployed frontend |
| `PYTHON_VERSION` | Optional, pins the Render Python version (e.g. `3.12.7`); `render.yaml` sets this already |

CORS depends on Vercel, and Vercel's API base URL depends on Render — deploy backend first,
copy its `*.onrender.com` URL into Vercel's `NEXT_PUBLIC_API_BASE_URL`, then come back and add
the real Vercel URL to `CORS_ALLOWED_ORIGINS` and redeploy the backend.

## Frontend — Vercel

Next.js on Vercel is close to zero-config: point Vercel at `frontend/` as the project root, it
auto-detects the framework, build command, and output directory. No code changes needed for
the deploy itself.

### Environment variables to set on Vercel

| Variable | Notes |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Same Supabase project as the backend |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase **anon** key (not service role — this one is public-safe) |
| `NEXT_PUBLIC_API_BASE_URL` | The Render backend URL, e.g. `https://ttths-buddy-backend.onrender.com` (no trailing slash) |
| `NEXT_PUBLIC_USE_MOCK_DATA` | **Must be set to `false`.** `frontend/src/lib/api.ts` treats *any unset or non-`"false"` value as mock mode* — this is not a safe-default flag, it defaults to mock ON. This exact gap caused a real incident (documented in `.env.example` / `requirements.md`) where the frontend silently served fake data for a full phase because this var wasn't set. Double-check it after every environment change on Vercel. |

Set these for the Production environment (and Preview, if you want preview deploys to hit
real data too — otherwise Preview will fall back to mock mode per the flag above).

## Deploy order

1. Deploy backend to Render first, using placeholder `CORS_ALLOWED_ORIGINS=http://localhost:3000` initially.
2. Note the Render service URL.
3. Deploy frontend to Vercel with `NEXT_PUBLIC_API_BASE_URL` set to that Render URL, and `NEXT_PUBLIC_USE_MOCK_DATA=false`.
4. Note the Vercel production URL.
5. Update `CORS_ALLOWED_ORIGINS` on Render to the real Vercel URL, redeploy the backend.
6. Smoke test: sign in on the deployed frontend, run a chat query, confirm it hits the real backend (Network tab should show requests to the Render URL, not mock data).
