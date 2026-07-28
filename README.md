# TTHS Buddy

TTHS Buddy is a scaffold for a legal study assistant focused on Vietnamese criminal procedure law. The current phase sets up the project structure, frontend and backend runtimes, environment validation, and a basic health check so later phases can add auth, ingestion, RAG, quiz, and dashboard features in order.

## Requirements

- Node.js 20+
- Python 3.11+
- Supabase project access
- Qdrant Cloud access

## Setup

1. Copy `.env.example` to `.env` at the repository root and fill in the required values.
2. Install frontend dependencies in `frontend/` with `npm install`.
3. Install backend dependencies in `backend/` with `pip install -r requirements.txt`.
4. Start the frontend with `npm run dev` from `frontend/`.
5. Start the backend with `uvicorn app.main:app --reload` from `backend/`.

Phase 1 covers the scaffold only. The ingestion pipeline, authenticated routes, RAG, quiz, and dashboard are reserved for later phases.
