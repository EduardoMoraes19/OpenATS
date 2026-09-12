# OpenATS Testing Guide

OpenATS uses three layers of automated tests: unit tests for pure logic, integration tests for the API and database, and end-to-end tests that drive a real browser through the running app. This guide explains what each layer does, which tools and databases they use, and how to run and write them.

## 1. Testing stack

| Tool | Used for |
| --- | --- |
| [pytest](https://docs.pytest.org) + [pytest-asyncio](https://pytest-asyncio.readthedocs.io) | Unit and integration tests (backend-py) |
| [httpx](https://www.python-httpx.org) (`ASGITransport`) | Sending HTTP requests directly into the FastAPI app inside integration tests, no server process needed |
| [Vitest](https://vitest.dev) + Testing Library | Unit and component tests (frontend) |
| [Playwright](https://playwright.dev) | End-to-end tests in a real browser |

Playwright is used instead of Selenium or Cypress because it can start the app itself, drives a real browser, and ships with a built-in debugging UI.

## 2. The three types of tests

### Unit tests

A unit test checks one function on its own. No database, no network, no browser. You give it an input and check the output.

```python
# backend-py/tests/unit/test_scoring.py
assert score_cv(parsed_cv, JobRequirements(skills=[])).match_score == 100
```

These run in milliseconds and tell you exactly which function is broken. Use them for pure logic such as formatting, validation rules, parsing, and calculations - `scoring.py`'s CV-match algorithm is the densest example in the codebase.

### Integration tests

An integration test checks several real parts working together: a route, its service, and a **real Postgres database**. `httpx.AsyncClient` with `ASGITransport` sends a genuine ASGI request into the FastAPI app - no server process binds to a port.

```python
# backend-py/tests/integration/test_core_flows.py
async def test_health_reports_db_and_redis_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["checks"] == {"db": "ok", "redis": "ok"}
```

These catch what unit tests cannot: real SQL errors, wrong column names, broken migrations, and dependency-order bugs (see `app/shared/auth/deps.py` for why decorator-level `dependencies=[]` matters). Use them for anything that touches the database.

### End-to-end (E2E) tests

An E2E test opens a real browser and uses the app the way a person would. The whole stack runs: Next.js frontend, FastAPI backend, and Postgres.

```ts
// e2e/careers.spec.ts
await page.goto("/careers");
await expect(page.getByRole("heading", { name: "Open roles" })).toBeVisible();
```

These are the slowest tests (seconds, not milliseconds) and they tell you the least about *where* a problem is, but they are the only tests that prove the app actually works for a real user. Keep them few and reserve them for critical paths.

### How many of each

Write many unit tests, some integration tests, and few E2E tests. Unit tests are fast and precise, so lean on them. E2E tests are slow and can be flaky, so keep them to the flows that would genuinely hurt if they broke.

## 3. Where tests live

```
OpenATS/
├── e2e/                          Playwright specs (repo root)
│   └── careers.spec.ts
├── playwright.config.ts          Playwright config (repo root)
├── tsconfig.json                 TypeScript config covering e2e/ only
└── backend-py/
    ├── pyproject.toml            pytest config lives under [tool.pytest.ini_options]
    ├── .env.test                 Test database connection (committed, dummy values only)
    └── tests/
        ├── conftest.py           The `client` fixture, `make_bearer_token`, per-test DB cleanup
        ├── unit/
        └── integration/
            └── helpers.py        Shared setup helpers (create_job, apply_candidate, ...)
```

Playwright lives at the repo root because an E2E test spans both `backend-py/` and `frontend/`, so it belongs to neither package.

## 4. Databases used by tests

This is the part worth understanding properly, because getting it wrong means tests write into your development data.

There are two Postgres containers: the dev one in the root `docker-compose.yml`, and the test one in its own `docker-compose.test.yml`.

| Container | Port | Database | Storage | Used by |
| --- | --- | --- | --- | --- |
| `openats-postgres` | 5432 | `openats` | Persistent volume | Normal development |
| `openats-postgres-test` | 5433 | `openats_test` | `tmpfs` (in memory) | Integration tests and E2E tests |

The test database uses `tmpfs`, so its data lives in memory and is wiped whenever the container restarts. That is intentional - and it means the schema has to be re-migrated after every container restart (see "First time setup" below).

**Integration tests** refuse to run against anything else: `tests/conftest.py` raises at import time unless `DATABASE_URL` contains `_test` or `:5433`, so a misconfigured run fails loudly instead of quietly truncating your dev data (every test truncates every app table beforehand via an autouse fixture).

**E2E tests** get the test database through `playwright.config.ts`, which passes `DATABASE_URL` to the servers it starts:

```ts
webServer: {
  command: "make dev",
  reuseExistingServer: false,
  env: { DATABASE_URL: "postgresql+asyncpg://openats:openats@localhost:5433/openats_test" },
}
```

This works because `backend-py/app/settings.py` uses `pydantic-settings`, which does not let its `env_file=".env"` default override a `DATABASE_URL` that is already set in the process environment.

> ⚠️ `reuseExistingServer` is set to `false` on purpose. If it were enabled and you already had `make dev` running, Playwright would attach to that server instead of starting its own, and that server reads `backend-py/.env`. The `DATABASE_URL` above would be silently ignored and the whole suite would quietly run against your development database. Stop `make dev` before running E2E tests.

### Redis

Redis is currently shared between development, integration tests, and E2E tests on port 6379. Integration tests clean up only their own `ratelimit:*` keys between runs (see `_clean_rate_limits` in `conftest.py`) rather than flushing the whole instance, specifically so this sharing stays safe. If a test starts exercising the CV analysis queue for real, give it a dedicated Redis database index (`redis://localhost:6379/1`) instead, so a job enqueued by a test can't be picked up by your development worker.

## 5. First time setup

Install dependencies:

```bash
pnpm install
pnpm exec playwright install chromium

cd backend-py
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cd ..
```

Start the test database and apply the schema to it:

```bash
docker compose -f docker-compose.test.yml up -d
cd backend-py
DATABASE_URL=postgresql+asyncpg://openats:openats@localhost:5433/openats_test .venv/bin/alembic upgrade head
cd ..
```

> ⚠️ Note the port is **5433**, not 5432. Using 5432 here points the migration at your development database instead.

Confirm the schema was applied:

```bash
docker exec openats-postgres-test psql -U openats -d openats_test -c '\dt'
```

## 6. Running the tests

### Backend unit and integration tests

```bash
cd backend-py
DATABASE_URL=postgresql+asyncpg://openats:openats@localhost:5433/openats_test .venv/bin/pytest tests/ -q
```

or, from the repo root:

```bash
make test     # backend (pytest) and frontend (vitest)
```

These can run at the same time as `make dev`. They never bind to port 8080.

### Frontend unit tests

```bash
pnpm test:frontend
```

### End-to-end tests

Stop `make dev` first, then:

```bash
make infra-up      # start Postgres and Redis
pnpm test:e2e
make test-e2e      # same as pnpm test:e2e
```

Playwright starts the backend on port 8080 and the frontend on port 3000 itself (via `make dev`), runs the specs, then shuts them down. If either port is already in use you will get an `EADDRINUSE` error, which means `make dev` is still running.

### Type checking the E2E tests

Playwright transpiles TypeScript without type checking, so a type error in an E2E spec will not fail the test run. Check them separately:

```bash
pnpm exec tsc --noEmit
```

## 7. Writing a new test

Decide which layer the test belongs to:

- Testing a single function with no database? Put it in `backend-py/tests/unit/`.
- Testing a route, a service, or a SQLAlchemy query? Put it in `backend-py/tests/integration/`.
- Testing something a user sees or clicks in the browser? Put it in `e2e/`.

pytest picks up any file matching `tests/**/test_*.py`. Playwright picks up any file in `e2e/`.

Integration tests share one database, and each one's autouse `_clean_database` fixture truncates every app table first - write tests assuming a clean slate, not assuming anything an earlier test left behind. Use `tests/integration/helpers.py`'s functions (`create_job`, `apply_candidate`, `manager_headers`, ...) instead of re-deriving the same multi-step setup in every test file.

For a new external dependency (R2, Gemini, the Google OAuth client), monkeypatch it at the boundary the code already calls through - see `test_upload.py` (`monkeypatch.setattr(r2_service, "upload_file", ...)`) or `test_integrations.py` (`monkeypatch.setitem(registry._REGISTRY, ...)`) for the pattern. Everything on the FastAPI side of that boundary still runs for real.

## 8. Debugging a failing test

For pytest, run a single file or a single test:

```bash
cd backend-py
DATABASE_URL=postgresql+asyncpg://openats:openats@localhost:5433/openats_test .venv/bin/pytest tests/integration/test_core_flows.py -q
DATABASE_URL=postgresql+asyncpg://openats:openats@localhost:5433/openats_test .venv/bin/pytest tests/integration/test_core_flows.py::test_health_reports_db_and_redis_ok -v
```

For Playwright, the interactive UI is the best tool. It shows a snapshot of the page at every step:

```bash
pnpm exec playwright test --ui         # interactive runner
pnpm exec playwright test --headed     # watch the real browser
pnpm exec playwright show-report       # HTML report after a failure
pnpm exec playwright test -g "careers" # run tests matching a name
```

## 9. Make sure your test can actually fail

A test you have never seen fail is a test you do not know works. After writing one, break the thing it is guarding and confirm it turns red.

For example, to confirm the E2E test that checks the backend API really does catch an unreachable backend:

```bash
OPENATS_API_URL=http://localhost:9999 pnpm test:e2e
```

That test should fail while the others still pass. This takes thirty seconds and it is the difference between real coverage and a test that only looks reassuring.

A concrete example from this project: the careers page catches its own fetch errors and falls back to an empty job list, so a completely dead backend renders exactly like "no jobs posted". A test that only checked the page loaded would pass through a total backend outage. That is why `e2e/careers.spec.ts` also asserts against `/public/jobs` directly.

## 10. Things to be aware of

- The E2E suite runs against an empty test database. Once you write tests that need job listings, candidates, or pipeline stages, seed the test database first (`cd backend-py && DATABASE_URL=... .venv/bin/python -m app.db.seed`, pointed at port 5433) or insert fixtures in a Playwright `beforeAll`.
- Frontend unit tests use their own Vitest install inside `frontend/` (jsdom + Testing Library), configured by `frontend/vitest.config.mts`. Run them with `pnpm test:frontend`.
- Authenticated E2E tests are not set up yet. Auth here is self-hosted JWT (see `backend-py/app/shared/auth/jwt_auth.py`), not a hosted identity provider, so this is more tractable than it used to be - a Playwright test could log in through the real `/login` form, or a fixture could mint a token directly with `create_access_token` and save it as browser storage state. Prefer testing `/public/*` routes for now, which skip authentication entirely.
