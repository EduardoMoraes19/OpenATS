# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenATS is a self-hosted applicant tracking system: `backend-py/` (Python/FastAPI) and `frontend/` (Next.js) are two independent projects, not a shared pnpm workspace — `frontend/` is the only pnpm package at the root. The root `Makefile` is what orchestrates both together (`make setup`, `make dev`, `make test`); see `CONTRIBUTING.md` for the full walkthrough.

`backend-py/` began as a from-scratch port of an earlier TypeScript/Express backend, ported module-for-module against the same Postgres schema. That original TypeScript backend has since been removed - `backend-py/` is the only backend now.

## Commands

### Backend (`backend-py/`)

```bash
.venv/bin/uvicorn app.main:asgi_app --reload --port 8080   # dev server
.venv/bin/python -m app.worker_main                          # CV analysis worker (arq), separate process
.venv/bin/pytest tests/ -q                                    # run the test suite
.venv/bin/pytest tests/integration/test_core_flows.py -v      # run one test file
.venv/bin/ruff check app                                       # lint
.venv/bin/mypy app                                               # type-check
.venv/bin/alembic revision --autogenerate -m "..."                # generate a migration (always review before committing)
.venv/bin/alembic upgrade head                                      # apply migrations to DB
.venv/bin/python -m app.db.seed                                       # seed pipeline stage templates (required on first setup)
.venv/bin/python -m app.db.create_admin --email ... --password ...      # bootstrap the first super_admin (no sign-up flow exists)
docker compose up -d                                                      # local Postgres (5432) + Redis (6379) + test Postgres (5433), see docker-compose.yml at the repo root
```

All of the above assume `cd backend-py` first and a virtualenv already created at `backend-py/.venv` (`python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`). `make setup`/`make dev`/`make test`/`make migrate`/`make seed`/`make create-admin` at the repo root wrap these for the common paths.

### Frontend (`frontend/`)

```bash
pnpm dev      # next dev --turbo, port 3000
pnpm build    # next build
pnpm lint     # eslint
```

## Architecture

### Backend

- **FastAPI** (async throughout - every route handler, service function, and DB call is `async def`). `uvicorn` runs it in dev with `--reload`; the same ASGI app is served in production via the Docker image (`Dockerfile.backend-py`).
- **Feature-first layout**: code is organized by feature under `app/modules/<feature>/`, each holding that feature's `router.py` (routes, FastAPI has no separate controller layer), `service.py` (business logic, no HTTP concerns - never raises unless it's an intentional `HTTPException`), and `schemas.py` (Pydantic request/response models, never the SQLAlchemy model itself in a response). 18 modules: `company`, `user`, `job`, `pipeline`, `hiring_team`, `custom_question`, `candidate`, `assessment`, `assessment_execution`, `offer`, `template`, `rejection`, `interview`, `integrations`, `chat`, `report`, `settings`, `upload`, plus `auth` for the self-hosted login/logout/change-password endpoints.
- **Request flow**: `app/main.py` (FastAPI app factory + Socket.IO ASGI mount) → `app/routes/api_router.py` (mounts every module under `/api`, with `get_current_user` + `api_limiter` applied once at this level, not per-route) or `app/routes/public_router.py` (`/public/*`, origin-gated instead of authenticated) → each module's `router.py` → that module's `service.py`.
- **Shared code**: `app/shared/auth/` is the single self-hosted-JWT verification path (`jwt_auth.py`), used by both HTTP (`deps.py`) and the Socket.IO handshake (`app/sockets/server.py`) so the two transports cannot drift on who counts as authenticated; `app/shared/services/` holds services used by 2+ modules (`mail_service`, `r2_service`, `google_calendar_service`) plus `ai_gateway.py` (multi-provider LLM gateway via OpenRouter - deliberately provider-agnostic and placed here even though `app/queues/cv_analysis/ai_client.py` is its only caller today, so any future AI feature has one gateway to import instead of a new SDK integration); `app/shared/integrations/` holds external-provider infra (`connection_service`, `registry`, `crypto`, `google_meet_provider`) — distinct from `modules/integrations/`, which is the CRUD/OAuth-callback feature for a user's configured integrations. Cross-module imports are fine; only promote to `shared/` when 2+ unrelated modules need it. Watch for circular imports between modules that embed each other's output shape (e.g. `offer/schemas.py` imports `CandidateOut` from `candidate/schemas.py`, so `candidate/schemas.py` can never import back from `offer/schemas.py` — build the merged response in the router instead, see `candidate/router.py`'s `_candidate_detail_dict`).
- `app/routes/job/router.py` also mounts the `pipeline`, `hiring_team`, and `custom_question` modules as sub-routers under `/jobs/{job_id}/...`.
- **Auth**: fully self-hosted, not a third-party IdP. `POST /api/auth/login` verifies a bcrypt password hash and issues an HS256 JWT (`sub`=user id, `role`, `tv`=token_version); `get_current_user` (`app/shared/auth/deps.py`) looks the user up by id, checks `is_active` and that `tv` still matches the DB row (so changing a password or role, or logging out, invalidates old tokens by bumping `token_version`). There is no JIT provisioning and no sign-up route - the first user is created directly with `python -m app.db.create_admin`, and every other user is created by an admin via `POST /api/users`.
- **Public routes** (`/public/*`) use origin-based access control (`app/shared/middleware/allowed_origins.py`), not auth. Assessment endpoints (`/public/assessment/:token`) use token-based auth instead.
- **Rate limiting**: a small dedicated Redis-backed limiter (`app/shared/rate_limit.py`) - no third-party library, because the authenticated API needs to key by **user id** rather than IP (so one office behind a NAT does not share a budget). `api_limiter` is applied once on `api_router`, `expensive_limiter` on uploads. Both are tunable with `RATE_LIMIT_API` / `RATE_LIMIT_EXPENSIVE`. **FastAPI resolves decorator-level `dependencies=[]` before parameter-level `Depends()` on the same route** - this matters when a limiter needs to key by the authenticated user: list `Depends(get_current_user)` first in the decorator's `dependencies=[]` so it runs (and is cached) before the limiter dependency does.
- **Per-job authorization**: `app/shared/auth/job_access.py` (`can_access_job`, `can_access_candidate`) gates both HTTP routes and Socket.IO handlers on hiring-team membership - the single source of truth for both transports. Job creation adds the creator to the hiring team, so membership is the app-wide notion of "your jobs". Authorization is *inconsistently applied by design*, ported as-is from the original: only the `chat` module actually calls these as a dependency; other modules do ad hoc `interviewer`-role checks inside their own service - don't "fix" this into consistency without being asked, it's intentionally preserved behavior.
- **Socket.IO**: `python-socketio`'s `AsyncServer` (`app/sockets/server.py`), mounted alongside FastAPI in `app/main.py` via `socketio.ASGIApp` so both HTTP and WS share one port - protocol-compatible with `socket.io-client`, so `frontend/lib/socket.ts` needed zero changes when the backend was rewritten. The handshake requires a valid JWT in `auth.token`, verified with the exact same `get_user_from_token` HTTP auth uses. Every authenticated socket joins the `staff` room. `join_job`/`join_candidate` are gated by `job_access.py` (`super_admin` exempt); chat-write handlers require the socket to *already be in that room* - membership is checked once at join time and cached per-connection, not re-checked on every message (a deliberate behavior to preserve, not a shortcut). System messages use a hardcoded `sender_id=1`. Chat `sentAt` timestamps must go through `to_utc_iso_z()` (`app/shared/schema.py`) like every other timestamp in the app - a raw `.isoformat()` omits the `Z` suffix the frontend's date parsing depends on (this was a real bug, found by a live cross-client parity check).
- Logger: stdlib `logging`, configured in `app/logging.py`.
- **Redis + arq**: CV analysis runs as a background job queue under `app/queues/cv_analysis/` (`queue.py` enqueues, `tasks.py` is the worker function + retry policy, `scoring.py` is the deterministic match-score algorithm, `ai_client.py` wraps the three AI calls - CV parsing, JD parsing, summary generation - built on the generic gateway in `app/shared/services/ai_gateway.py`). Retry policy mirrors the original BullMQ config: 3 attempts, exponential backoff (5s, 10s), and only the exhausted final attempt marks the DB row `failed` - intermediate retries touch nothing. **Any blocking call inside an `async def`** (boto3's R2 client, in particular) **must go through `asyncio.to_thread`**, or it freezes the entire event loop for every concurrent request/job, not just its own - this has been a real, repeated bug (`r2_service.upload_file`/`download_file`/`delete_by_url` all needed this fix after being added as plain synchronous calls).

### Database

- PostgreSQL via **SQLAlchemy 2.0** (async) + **Alembic**. Models live in `app/db/models/` (one file per domain), matching the original 33-table/16-enum schema exactly - every `timestamp` column is `DateTime(timezone=False)` (naive, always a UTC instant in practice; see `to_utc_iso_z()` for why the API layer must add the `Z` back on the way out).
- When changing the schema: run `alembic revision --autogenerate -m "..."` in `backend-py/`, **review the generated migration** (autogenerate misses some things - renamed columns look like drop+add, for one), then commit it.
- The 7 default pipeline stage templates - required for job creation to work (`job/service.py` clones them into `job_pipeline_stages` on every new job) - are seeded by migration `0003_seed_pipeline_stages`, so a fresh `alembic upgrade head` is enough on its own. `app/db/seed.py` (`make seed`) does the same insert (delete-then-recreate) and stays useful for resetting templates back to default on an existing database.
- **Local Postgres + Redis**: `docker-compose.yml` at the repo root runs the dev Postgres and Redis as containers (`openats`/`openats`/`openats` for user/password/db; Redis with no auth); `docker-compose.test.yml` runs a separate `tmpfs`-backed Postgres on port 5433 for tests. See `CONTRIBUTING.md` for the full setup flow.

### Frontend

- **Next.js** with `force-dynamic` on the root layout (`frontend/app/layout.tsx`) — the whole app is SSR-disabled. This predates the auth migration below; its original justification (`AsgardeoProvider` needing request context) no longer applies since that provider was removed, but removing `force-dynamic` itself hasn't been verified safe and shouldn't be done incidentally.
- Heavy components are code-split with `ssr: false` via `frontend/components/dynamic-imports.tsx`.
- **Tailwind v4** — CSS-first config (`@tailwindcss/postcss`), no `tailwind.config.ts`. Theme defined via `@theme` in CSS globals.
- **shadcn/ui** with `base-vega` style. Icon library is **hugeicons** (not lucide or heroicons).
- Path alias: `@/*` → `./*` (configured in both `tsconfig.json` and Next.js config).
- **Auth**: self-hosted JWT, not a third-party IdP. `frontend/lib/session.ts` manages an httpOnly session cookie (`openats_session`) holding the backend's own access token; `frontend/app/login/actions.ts` has the login/logout Server Actions; `frontend/proxy.ts` (Edge middleware) checks the cookie's *presence* only, not its validity - the backend is the real enforcement point. The one deliberate exception to httpOnly is `/api/socket-token`, which hands the raw token to browser JS because the Socket.IO client needs it directly.
- **Server-side data fetching**: `serverFetch` in `frontend/lib/auth-action.ts` using `React.cache()` for auth context.
- **Client-side data fetching**: `useApi` hook + React Query hooks in `frontend/hooks/queries/`.
- **Component placement convention**: components/hooks/utils scoped to one route live colocated under that route using Next.js's underscore-prefixed folders (excluded from routing) — `_components/` (nest further for large features, e.g. `templates/_components/template-form/email-builder/`), `lib/` (singular — not `libs/`), `hooks/`. Only truly shared code goes in the top-level `frontend/components/` (shadcn primitives in `components/ui`, shared `components/table`), `frontend/lib/`, and `frontend/hooks/queries/`.

## Testing

See `docs-draft/TESTING.md` for the full guide. In short:

- **Backend unit + integration tests** use pytest and live in `backend-py/tests/` (`unit/`, `integration/`). Integration tests send requests straight into the FastAPI app via `httpx.AsyncClient(transport=ASGITransport(...))` - no server process binds a port. `tests/conftest.py` refuses to run unless `DATABASE_URL` points at the test database (contains `_test` or `:5433`), and truncates every app table before each test.
- **End-to-end tests** use Playwright and live in `e2e/` at the repo root, because they span both packages. Config is `playwright.config.ts` (`webServer.command: "make dev"`), and `tsconfig.json` at the root covers them.
- **Integration tests hit a real database**: a separate Postgres on port **5433** (`postgres-test` in `docker-compose.yml`, `tmpfs`-backed so it resets on container restart), never the dev database on 5432.
- `backend-py/.env.test` is committed on purpose. It holds no secrets, only dummy values, so that tests pass on pull requests from forks (GitHub never gives secrets to those).
- E2E tests also use the 5433 database, via `webServer.env` in `playwright.config.ts`. `reuseExistingServer` is `false` so an already-running `make dev` cannot be adopted, which would silently point tests at the dev database. **Stop `make dev` before running E2E.**
- Commands: `make test` (backend pytest + frontend vitest), `pnpm test:frontend`, `pnpm test:e2e` (Playwright), `pnpm exec tsc --noEmit` (type-check the E2E specs, which Playwright does not do).
- CI runs two parallel jobs on every pull request (`.github/workflows/test.yml`): `test-backend` (ruff, mypy, pytest) and `test-frontend` (eslint, vitest, e2e-spec type-check). Neither uses secrets.
- **Frontend tests** use a separate Vitest install in `frontend/` with jsdom and Testing Library, in `frontend/tests/`. They cover pure helpers and rendered components; there is no network or router mocking set up yet.
- **External dependencies in tests** (R2, the AI gateway, the Google OAuth client) are monkeypatched at the exact boundary the app code calls through, not mocked deeper - see `test_upload.py` or `test_integrations.py` for the pattern. Everything on the FastAPI side of that boundary runs for real, including the database.

## Roadmap

`docs-draft/GA_ROADMAP.md` tracks everything remaining before v1.0, grouped by release, with a status on every item (🔴 Planned, 🟡 In progress, 🟢 Done).

**When you complete work that appears on that roadmap, update the item's status in the same change.** If you finish something that is not listed, add a row for it. An out-of-date roadmap is worse than none, because it states things that are not true.

## Environment Variables

Two separate `.env` files are required (copy from `.env.example` in each directory):

- `backend-py/.env` — `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY` (signs/verifies JWTs), `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `ENCRYPTION_KEY`, `FRONTEND_URL`, `R2_*`, `RESEND_*`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_CALENDAR_ID`, `GOOGLE_OAUTH_*`
- `frontend/.env` — `OPENATS_API_URL`, `NEXT_PUBLIC_API_URL` (that's the whole file now - no auth-related variables live here anymore)

Startup fails fast (`app/settings.py`, validated eagerly before any DB/Redis connection opens) with a clear message if a required backend variable is missing, rather than crashing later on the first request that needs it.

## CI/CD

- `.github/workflows/deploy.yml` deploys `backend-py/` to an Azure VM on push to `main` (when `backend-py/**`, `Dockerfile.backend-py`, or `docker-entrypoint-py.sh` change): SSH → `git reset --hard` → `docker build -f Dockerfile.backend-py` → restart two containers (`openats-api`, `openats-worker`, same image, different command) with `--network host` so they reach whatever Postgres/Redis the VM already points `backend-py/.env` at. `backend-py/.env` must already exist on the VM with real production secrets - this deploy never creates or edits it.
- No CI or deploy workflow for the frontend yet.
- Only `frontend/` has ESLint. `backend-py/` is linted with `ruff` and type-checked with `mypy` instead.
