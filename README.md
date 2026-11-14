# ChronoGuard — Lunar Crew Health Companion

A full-stack lunar mission health console: a FastAPI/SQLModel backend with a
PostgreSQL runtime database (Neon), a deterministic mission-intelligence module,
and a React/Vite frontend with an Observation Deck UI.

## Quick start

### Backend

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# edit backend/.env and set DATABASE_URL to your PostgreSQL instance
uvicorn app.main:app --reload
```

SQLite remains the fallback for tests and local boot when `DATABASE_URL` is unset.
The schema is created on startup. See [`backend/README.md`](backend/README.md) for
the full API, PostgreSQL operations, analysis engine, mission clock, and
scientific caveats.

Seed demo data (and optionally run the configured analysis engine):

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.seed.demo_data --scenario normal_routine --reset --analyze
```

### Frontend

```powershell
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

Open <http://127.0.0.1:5173>. The client reads the real backend API and creates the
demo crew on first load when `VITE_AUTO_PROVISION_CREW=true` (the default).

## Checks

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm run build
npm run lint
```

## Layout

- `backend/` — FastAPI app, SQLModel models, analysis engine, mission-intelligence
  module, PostgreSQL/SQLite database layer, tests.
- `frontend/` — React/Vite UI, API client, offline write queue, mock design
  fixtures.

The backend README documents the unified `422` shape, `X-Total-Count` list headers,
crew lifecycle, assessment detail, analysis runs, dashboard summary, mission
filters, and check-in `source` rules.
