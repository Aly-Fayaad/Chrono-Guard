# Deployment guide — Vercel (frontend) + FastAPI Cloud (backend)

This project is a monorepo:

```
ChronoGuard/
├── frontend/   → Vercel project (Vite/React)
└── backend/    → FastAPI Cloud project (FastAPI/SQLModel)
```

Development worked because the browser, the Vite dev server and the API all ran
on `localhost`. Production breaks unless the **three** pieces below agree:

| Piece | Value |
| --- | --- |
| Frontend build variable | `VITE_API_BASE_URL` = `https://<backend-host>/api/v1` |
| Backend `CORS_ORIGINS` | the exact frontend origin, e.g. `https://chrono-guard-hazel.vercel.app` |
| Backend `ALLOWED_HOSTS` | the backend host, e.g. `*.fastapicloud.dev` |

The code now defaults these correctly, but the deployment hosts still have to be
set in each dashboard.

## What was actually wrong

1. **Frontend ignored the env variable.** `src/api/client.ts` read
   `import.meta.env.API_BASE_URL`, but Vite only exposes variables prefixed with
   `VITE_`. So `VITE_API_BASE_URL` set in Vercel had no effect and every
   production request went to `http://127.0.0.1:8000/api/v1` — the visitor's own
   machine. Fixed to read `VITE_API_BASE_URL`.
2. **CORS origin had a trailing slash.** The default was
   `https://chrono-guard-hazel.vercel.app/`. Browsers send
   `Origin: https://chrono-guard-hazel.vercel.app` and CORS matching is exact, so
   the deployed frontend was rejected. Fixed (trailing slashes are stripped).
3. **Host header allow-list blocked the deployment.** `ALLOWED_HOSTS` defaulted to
   `localhost,127.0.0.1,testserver`, so every request to
   `https://<app>.fastapicloud.dev` got `400 Invalid host header`. The default
   now includes `*.fastapicloud.dev`, and the deployed host is also derived from
   FastAPI Cloud's `FASTAPI_PUBLIC_URL`.
4. **Production settings crashed at startup.** With `ENV=prod`, the old validator
   raised if any `http://localhost` origin or host was present. The local
   `backend/.env` had exactly that, so the app could not boot in production mode.
   Non-HTTPS CORS origins are now ignored in production instead of killing the
   process; local Host entries are kept because platform health checks often call
   the container directly (`Host: localhost`). Only a missing PostgreSQL URL or
   an empty CORS list still fails fast.
5. **Fresh production database had no crew.** The backend only auto-seeds in
   development. `ensureCrew()` was disabled by default, so `GET /overview`
   returned `404` and the UI showed "Couldn't load health data". Auto-provisioning
   is now enabled unless `VITE_AUTO_PROVISION_CREW=false`.
6. **`/demo/seed` is 403 in production** (by design). Use `POST /crew` once, or
   leave auto-provisioning on.

## 1. Deploy the backend (FastAPI Cloud)

FastAPI Cloud URLs look like `https://<name>.fastapicloud.dev` (note `.dev`, not
`.com`).

### Project settings

- **Application Directory:** `backend`
  (Dashboard → Settings → Application Directory. Required for this monorepo.)
- Framework detection: `app/main.py` is a standard location, so FastAPI Cloud
  resolves `app.main:app` automatically.
- `backend/.python-version` pins Python `3.12`.
- `backend/requirements.txt` now installs `fastapi[standard]`, which also provides
  the `fastapi deploy` CLI locally:

```powershell
cd D:\Nasa\ChronoGuard\backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
fastapi login
fastapi deploy
```

`backend/.env` is gitignored, so it is **not uploaded**. Configure the same values
in the FastAPI Cloud dashboard (Environment Variables) or with the CLI:

```powershell
fastapi cloud env set ENV prod
fastapi cloud env set --secret DATABASE_URL "postgresql://user:pass@host:5432/db?sslmode=require"
fastapi cloud env set CORS_ORIGINS "https://chrono-guard-hazel.vercel.app"
fastapi cloud env set MISSION_EPOCH "2026-10-30T07:00:00Z"
fastapi cloud env set MISSION_DAY_HOURS "24.65"
fastapi cloud env set ANALYSIS_ENGINE "app.ml.crew_health_engine:CrewHealthEngine"
fastapi deploy
```

`ALLOWED_HOSTS` does not need to be set for the default FastAPI Cloud domain:
the default already includes `*.fastapicloud.dev`, and the exact host is also
derived from `FASTAPI_PUBLIC_URL`. Only set it for a custom API domain or to
tighten the list.

Variable reference:

| Variable | Production value | Why |
| --- | --- | --- |
| `ENV` | `prod` | Enforces PostgreSQL, disables `/demo/seed`. |
| `DATABASE_URL` | Neon/PostgreSQL URL | SQLite is ephemeral and unsafe with multiple instances. Required when `ENV=prod`. |
| `CORS_ORIGINS` | `https://chrono-guard-hazel.vercel.app` | Exact browser origin, **no trailing slash**. Comma-separate more origins. |
| `CORS_ORIGIN_REGEX` | optional, e.g. `https://chrono-guard-.*\.vercel\.app` | Allows Vercel preview deployments. |
| `ALLOWED_HOSTS` | optional; `*.fastapicloud.dev` is already the default | Host-header allow-list. Add a custom API domain here. |
| `MISSION_EPOCH`, `MISSION_DAY_HOURS` | `2026-10-30T07:00:00Z`, `24.65` | Mission clock defaults; only set if you want to override. |
| `ANALYSIS_ENGINE` | `app.ml.crew_health_engine:CrewHealthEngine` | Analysis engine; use `app.services.analysis:NullEngine` to disable. |

### Verify

```powershell
curl https://<name>.fastapicloud.dev/health
# {"status":"ok","env":"prod"}
curl https://<name>.fastapicloud.dev/health/ready
# {"status":"ok","database":"ok","dialect":"postgresql","env":"prod"}
```

If `/health` returns `400 Invalid host header`, `ALLOWED_HOSTS` is still wrong.
If the deployment fails to start, check the build logs for a configuration error
(most commonly a missing/`sqlite` `DATABASE_URL` with `ENV=prod`).

## 2. Deploy the frontend (Vercel)

Project settings:

- **Root Directory:** `frontend`
- **Framework preset:** Vite
- **Build command:** `npm run build` (default)
- **Output directory:** `dist` (default)

Environment variable (Settings → Environment Variables, Production **and**
Preview):

```
VITE_API_BASE_URL = https://<name>.fastapicloud.dev/api/v1
```

Optional:

```
VITE_AUTO_PROVISION_CREW = false   # only if you create crews yourself
```

Important: Vite **inlines** `VITE_*` values at build time. After changing the
variable you must trigger a new deployment (Redeploy); editing the variable alone
does not update the already-built bundle.

`/api/v1` is appended automatically if you paste only the host, and stripped of
trailing slashes, but the explicit `https://<name>.fastapicloud.dev/api/v1` form
is recommended.

### Verify

Open the site and check DevTools → Network:

- Requests go to `https://<name>.fastapicloud.dev/api/v1/...`
- Responses include `access-control-allow-origin: https://chrono-guard-hazel.vercel.app`
- `GET /api/v1/crew/crew-demo-01/overview` returns `200`

If the first request is `404` for the crew, the database is empty. Either leave
`VITE_AUTO_PROVISION_CREW` unset/`true`, or create the demo crew once:

```powershell
curl -X POST https://<name>.fastapicloud.dev/api/v1/crew `
  -H "Content-Type: application/json" `
  -d '{\"id\":\"crew-demo-01\",\"display_name\":\"Luna Park\",\"role\":\"Flight Engineer\"}'
```

## 3. Troubleshooting map

| Browser / log message | Cause | Fix |
| --- | --- | --- |
| `Could not reach the backend` after 15 s | Bundle still points at `http://127.0.0.1:8000` | Set `VITE_API_BASE_URL` in Vercel and redeploy. |
| `blocked by CORS policy` / no `access-control-allow-origin` | Origin mismatch (scheme, `www`, port, trailing slash, preview domain) | Put the exact origin in `CORS_ORIGINS`; add `CORS_ORIGIN_REGEX` for previews. |
| `400 Invalid host header` | `ALLOWED_HOSTS` missing the API host | Set `ALLOWED_HOSTS=*.fastapicloud.dev` (plus any custom domain). |
| `500` on every request / deployment never becomes healthy | `ENV=prod` with a SQLite or missing `DATABASE_URL` | Set the managed PostgreSQL URL. |
| Data disappears after each deploy | SQLite file on an ephemeral filesystem | Use PostgreSQL. |
| `403 Demo seeding is disabled` | `/demo/seed` is dev-only | Create the crew with `POST /crew` (auto-provision does this). |
| Frontend works locally but not in production | `.env.local` is not used by Vercel | Configure the variable in the Vercel dashboard. |

## 4. Security note

`backend/.env` contains a live Neon password and must never be committed (it is
gitignored). If that file has ever been shared or pushed, rotate the database
password in Neon and update the FastAPI Cloud secret. In production, mark
`DATABASE_URL` as a secret in the FastAPI Cloud dashboard.
