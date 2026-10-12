# Deployment guide — Vercel (frontend) + Render (backend)

Manual setup via each dashboard. Nothing in this doc auto-deploys; it's a checklist plus the
files in this repo that make the dashboard steps line up.

## Backend — Render

### Live URLs

| | URL |
|---|---|
| Backend (Render) | `https://tths-buddy.onrender.com` — health: `/api/health` |
| Frontend (Vercel) | `https://tths-buddyy.vercel.app` |

Note the spelling: the backend host is **`tths-`** (two `t`s, not three) and the Vercel host ends
in **`buddyy`** (two `y`s). Guessing `ttths-buddy-backend.onrender.com` returns Render's own 404
page, which looks exactly like a service that is down — this cost a diagnosis pass on
2026-10-12 before the real URL was confirmed.

### Instance Type: Free (this is load-bearing)

The deployed service runs on Render's **Free** instance type, created by hand in the Dashboard.
`render.yaml` claimed `starter` until 2026-10-12; that was never the running configuration.

The Free tier **spins the service down after ~15 minutes with no inbound requests**, and the
next request has to wait for the instance to boot before it is served. Measured on 2026-10-12
against `GET /api/health` — the cheapest endpoint there is, no auth, no DB, no Gemini — after a
22-minute idle period:

| Measurement | Cold (first request after spin-down) | Warm (next 3 requests) |
|---|---|---|
| Round 1, after 22.7 min idle | **46.45s** | 0.21s / 0.20s / 0.21s |
| Round 2, after 22.1 min idle | **44.14s** | 0.19s / 0.27s / 0.18s |

So the boot itself costs roughly **44-46 seconds** — reproducible across two independent idle
periods, not a one-off — and it is paid by whoever happens to arrive first. A real chat question on a warm instance measured 12.98–14.18s (median 13.56s, n=5), which
means the worst case a student actually sees is boot + answer ≈ **60 seconds**, with nothing on
screen for most of it. Practical consequences:

- The first student to open the app after a quiet period waits for a boot, on top of the normal
  request time. This is a property of the plan, not a bug in the code.
- `/api/health` is the cheapest thing to hit to trigger (or absorb) that boot — the frontend
  warm-up ping uses it.
- Anything that measures or compares production latency has to state whether the sample was
  cold or warm, or the numbers mean nothing.
- Upgrading the Instance Type is the only real fix; everything else only hides the wait.

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

**Why `-w 2` (not the usual `2×CPU+1`):** Render's Free tier caps RAM at 512MB. More
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
| `GEMINI_CHAT_MODEL_COMPLEX` | **Deliberately NOT set on Render.** Optional stronger model for the final generation call on long/tình huống questions (>250 chars). Leaving it unset makes `resolved_complex_chat_model` fall back to `GEMINI_CHAT_MODEL`, which is what production does today. Do not add it without re-measuring first — see the warning below. |
| `QDRANT_URL` | Qdrant Cloud cluster URL |
| `QDRANT_API_KEY` | Qdrant Cloud API key — **secret** |
| `QDRANT_COLLECTION` | e.g. `ttths_law_chunks` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated. Must include the real Vercel URL (`https://tths-buddyy.vercel.app`) — defaults to `http://localhost:3000` if unset, which will block the deployed frontend |
| `PYTHON_VERSION` | Optional, pins the Render Python version (e.g. `3.12.7`); `render.yaml` sets this already |

**Do not set `GEMINI_CHAT_MODEL_COMPLEX` on Render without re-measuring.** Measured locally on
2026-10-12 against the 4 `tinhhuong` bank questions and a 573-char scenario question: with
`gemini-3.1-pro-preview` configured, that model failed to return a first token within the 18s
deadline on 2 of 4 bank questions (6 of 6 on the synthetic one), so each of those requests
burned the full 18s and then re-generated on `gemini-3.1-flash-lite` anyway. Mean time per
question was 28.38s with the preview model vs 14.87s without it (1.91x), while answer quality
was indistinguishable — same 2/4 ground-truth Điều cited in both arms, same conclusions, and the
2 misses were retrieval failures (the Điều was never retrieved) that the generation model cannot
affect. Retrieval itself never used this model: HyDE and re-ranking both go through
`generate_answer`, which is hardcoded to `GEMINI_CHAT_MODEL`.

So on today's evidence the preview model costs ~2x latency for no measurable quality gain. If it
is ever reconsidered, re-run that comparison first — preview-tier capacity changes over time.

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
