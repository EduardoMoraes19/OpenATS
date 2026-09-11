# OpenATS Road to GA

This is the plan for getting OpenATS to `v1.0.0` (general availability). It tracks what is left, why each item matters, and what is already done.

Current version: **v0.5.0**

## Status legend

| Status | Meaning |
| --- | --- |
| 🔴 Planned | Not started |
| 🟡 In progress | Being worked on now |
| 🟢 Done | Shipped |

---

## v0.5.0 - Fix what is broken

The focus of this phase is correctness and safety, not new features. Nothing here adds functionality, it makes what already exists trustworthy.

### Security

| Item | Why it matters | Status |
| --- | --- | --- |
| Authenticate Socket.IO connections | Sockets currently accept **any** connection with `cors: "*"` and no auth. An anonymous client can emit `send_job_message` with any `senderId` and write to the database impersonating a user. **This is the one true GA blocker.** | 🟢 Done |
| Scope socket broadcasts to rooms | `notifyStageChanged`, `notifyOfferChanged`, and `notifyInterviewChanged` use `io.emit()` with no room, so every connected client receives candidate pipeline movements, offers, and interviews. | 🟢 Done |
| Take `senderId` from the JWT, not the payload | The client currently supplies its own user id on socket writes. | 🟢 Done |
| Authorize socket room joins | Sockets now require authentication, but any logged-in user can still `join_job` for a job they are not on the hiring team for. Authentication closed the public hole, this closes the internal one. | 🟢 Done |
| Re-check socket tokens on reconnect | The token is read once when the dashboard layout renders. If it expires while a tab is open, reconnects fail silently and realtime stops until the page is refreshed. | 🟢 Done |
| Authorize chat history over HTTP | `GET /chat/job/:jobId` and `/chat/candidate/:candidateId` return any conversation to any authenticated user. The socket rooms are now gated, so this is the remaining way to read another hiring team's chat. | 🟢 Done |
| Rate limit authenticated routes | Only `/public/*` is rate limited today. | 🟢 Done |
| Resolve dependency vulnerabilities | 54 reported (15 high). Every high comes through `next@16.1.6`, the only direct dependency involved: bumping it to `>=16.2.11` also clears the `sharp` and `postcss` copies it pins. `dompurify` arrives via `@asgardeo/react` and needs a `pnpm.overrides` entry or an upstream fix. Do this last, right before release, so the version bump is fresh. | 🔴 Planned |

### Deployment

🟢 **Complete and verified in production on 6 Aug 2026.** A deliberate change to the `/health` response string was pushed and confirmed live at `api.openats.dev`, proving the VM now receives new code. Before this, deploys had been silently failing since at least 3 Aug 2026 while reporting success.

| Item | Why it matters | Status |
| --- | --- | --- |
| Add `set -e` to the deploy script | Without it, failed steps still report success because only the last command sets the exit code. Deploys have been silently failing since at least 3 Aug 2026. | 🟢 Done |
| Use `git reset --hard origin/main` | The VM has drifted (locally modified `pnpm-workspace.yaml`, stray `pnpm-lock.yaml`), which makes `git pull` abort. A hard reset removes drift permanently. | 🟢 Done |
| Install from the repo root, not `backend/` | The deploy still installs from `backend/`, which is wrong since the pnpm workspace conversion. | 🟢 Done |
| Health check after restart | `curl -fsS http://localhost:8080/health` at the end, so a crash-looping process does not report a green deploy. | 🟢 Done |
| Gate deploy on tests passing | `test.yml` and `deploy.yml` are independent, so a red build still deploys. | 🟢 Done |

### Testing

| Item | Why it matters | Status |
| --- | --- | --- |
| Tests for authentication | Login broke completely in v0.4.0 and nothing would have caught it. 17 tests in `tests/integration/auth.test.ts` now cover token validity, claims, provisioning, and the middleware. Only the JWKS fetch is mocked, so signature/issuer/expiry are genuinely verified. Confirmed to bite by reintroducing the v0.4.0 `sub`-change bug and watching only that test fail. | 🟢 Done |
| Tests for core flows | Apply to a job, move pipeline stage, send an offer, schedule an interview. 11 tests in `tests/integration/core-flows.test.ts` drive the real HTTP API end to end with a signed token. Writing them found a live bug: a partial `PATCH /offers/:id` wiped `startDate`, leaving the offer unsendable. Fixed, with a regression test. | 🟢 Done |
| Frontend tests | None existed. Vitest + Testing Library + jsdom are set up in `frontend/`, with 24 tests covering `buildJobPayload`, the offer formatting helpers, and one rendered component to prove the React half works. | 🟢 Done |
| Coverage reporting | Without it, "how much is tested" is guesswork. `pnpm test:coverage` runs v8 coverage on the backend (text, html, lcov). Baseline is 20% statements overall, 94% on `shared/auth`. | 🟢 Done |
| Type-check tests in CI | `tsconfig.test.json` inherited `"exclude": ["tests"]` from the base config, so it checked nothing; a deliberate type error sat in `object.util.test.ts` and passed. Config fixed and `test.yml` now runs it as its own step, verified with a canary error. | 🟢 Done |

### Tooling

| Item | Why it matters | Status |
| --- | --- | --- |
| Add linting to the backend | There is no ESLint config or script, and `pnpm lint` at the repo root currently **fails** with `ERR_PNPM_RECURSIVE_RUN_NO_SCRIPT`. Now configured, passing with 0 problems, and gated in CI. | 🟢 Done |
| Call `validateEnv()` in `worker.ts` | The API validates its environment on boot, the worker does not, so it can start with broken config and fail later at job time. | 🟢 Done |
| Fix the frontend's lint errors | 112 errors, of which 91 were `no-explicit-any` (not `set-state-in-effect` as first recorded). All are now fixed and root `pnpm lint` exits 0, so lint can become a CI gate. Two `react-hooks/set-state-in-effect` cases carry a scoped `eslint-disable` with the reason in a comment: both mutate state (a pending-moves map, a module-level id counter) that cannot legally move into render. 35 warnings remain, mostly unused vars. | 🟢 Done |
| Remove `any` from the backend | 108 uses, mostly `catch (e: any)` and `(e as any).message`. All replaced with narrowed helpers, so `no-explicit-any` is an **error** and the backend has none. | 🟢 Done |
| Add `CHANGELOG.md` | Release notes only existed on GitHub. All five releases are now reproduced in the repo in Keep a Changelog format, with an `[Unreleased]` section tracking the v0.5.0 work. | 🟢 Done |

---

## Backend rewrite: Python (FastAPI)

`backend-py/` was a from-scratch port of the original TypeScript/Express
backend to FastAPI + SQLAlchemy + Alembic, built module-for-module against
the same 33-table Postgres schema. As of the cutover below, it **is** the
backend - the original TypeScript implementation has been deleted.

| Item | Why it matters | Status |
| --- | --- | --- |
| All 18 business modules ported | company, user, job, pipeline, hiring-team, custom-question, candidate, assessment, assessment-execution, offer, template, rejection, interview, integrations, chat, report, settings, upload. | 🟢 Done |
| Self-hosted JWT auth (backend + frontend) | Replaced Asgardeo entirely - bcrypt password hashes, HS256 tokens, `token_version` for session invalidation. `frontend/` now only speaks to `backend-py/`; it no longer carries any Asgardeo dependency. | 🟢 Done |
| Cross-parity HTTP harness | Ran the same sequence of authenticated calls against both backends against identical seeded data and diffed responses field-by-field. Found and fixed 11 real wire-format divergences (public job/offer shapes, interview fields, candidate detail composition, a report date-boundary bug). | 🟢 Done |
| Socket.IO live parity check | Connected a real `socket.io` client to both backends with equivalent JWTs, joined rooms, sent chat messages, and diffed the emitted events. Found and fixed one real bug: chat `sentAt` was missing the `Z` suffix the frontend's date parsing depends on. | 🟢 Done |
| CI for `backend-py` | `test.yml` now runs `ruff`, `mypy`, and the full `pytest` suite on every PR, in parallel with the existing TS job. Before this, a regression here would only surface if someone ran the tests locally. | 🟢 Done |
| `Dockerfile.backend-py` build verified | Built the image and ran both the API and the arq worker command against a real Postgres/Redis - migrations apply, health check passes, worker connects. Never confirmed to actually run before this. | 🟢 Done |
| Test coverage for `hiring_team`, `upload`, `integrations`/OAuth | Had zero tests anywhere. `test_hiring_team.py`, `test_upload.py`, `test_integrations.py` now cover list/add/remove and the job-creator-can't-be-removed rule, staff and public resume/logo upload (validation, auth, the `company.logoUrl` side effect), and the full OAuth callback (success, missing params, invalid state, a rejected code) - R2 and the Google client are monkeypatched at their boundaries, everything else is real. | 🟢 Done |
| Test coverage for the CV analysis worker | Only the scoring math (`test_scoring.py`) was tested. `test_cv_analysis_worker.py` now covers `run_analysis`'s not-a-resume rejection, the non-fatal AI-summary failure, successful scoring/persistence, and the arq task's retry-vs-exhaustion bookkeeping (R2 and Gemini monkeypatched). Found and fixed one more bug while writing it: `run_analysis` called `r2_service.download_file` - a blocking boto3 call - directly instead of through `asyncio.to_thread`, the same event-loop-freezing bug already fixed for uploads. | 🟢 Done |
| Cutover: remove `backend/`, `backend-py/` is the only backend | The TypeScript implementation, its Dockerfile/entrypoint, and `setup-asgardeo.sh` are deleted. `pnpm-workspace.yaml`, root `package.json`, `.github/workflows/test.yml` (now `test-frontend` + `test-backend`), `playwright.config.ts`, `CLAUDE.md`, `README.md`, `CONTRIBUTING.md`, and `docs-draft/TESTING.md` all updated to describe `backend-py/` as the one true backend. Verified post-cut: `make test` (84 backend + 24 frontend), `make lint`, `make build`, and a fresh `docker build -f Dockerfile.backend-py` all pass from a clean checkout. | 🟢 Done |
| `deploy.yml` rewritten for Docker, not yet exercised against the real VM | SSH → `docker build -f Dockerfile.backend-py` → restart two `--network host` containers (api + worker). Requires `backend-py/.env` to already exist on the VM with real secrets (carried over from the old pm2/Node deploy) and Docker to be installed there - neither has been confirmed on the actual box, only reasoned through and YAML-validated locally. Watch the first deploy closely. | 🟡 In progress |

---

## v1.0.0 - General availability

The "do it properly" phase. None of this is urgent, all of it is what separates a working project from one people rely on.

| Item | Why it matters | Status |
| --- | --- | --- |
| Build artifacts in CI | Compiling TypeScript on the production VM is how the current drift happened. Build once in CI, ship the result. | 🔴 Planned |
| Rollback mechanism | There is no way back from a bad deploy except another deploy. | 🔴 Planned |
| Staging environment | Every change currently goes straight to production. | 🔴 Planned |
| Error tracking | Console-only logging means a user-reported error cannot be investigated. | 🔴 Planned |
| Structured logging | File transports in `utils/logger.ts` are commented out. | 🔴 Planned |
| Security review | Before telling anyone to run this with real candidate data. | 🔴 Planned |
| Complete documentation | Deployment guide, configuration reference, upgrade guide. | 🔴 Planned |

---

## Completed

### v0.4.0 (5 Aug 2026)

| Item | Status |
| --- | --- |
| Backend reorganized into feature modules (`src/modules/`, `src/shared/`) | 🟢 Done |
| Fixed login failing when the Asgardeo `sub` changes | 🟢 Done |
| Fixed the logger silently dropping error details at 41 call sites | 🟢 Done |
| Fixed the backend not compiling (duplicate `ioredis` versions) | 🟢 Done |
| Vitest set up for unit and integration tests | 🟢 Done |
| Playwright set up for end-to-end tests | 🟢 Done |
| Isolated test database on port 5433 | 🟢 Done |
| CI running tests, type check, and build on every pull request | 🟢 Done |
| Testing guide (`docs/TESTING.md`) | 🟢 Done |
| Restored 91 accidentally deleted lines in `CONTRIBUTING.md` | 🟢 Done |

---

## Keeping this file current

When you finish something on this list, update its status in the same pull request as the work. A roadmap that is not updated is worse than no roadmap, because it tells people things that are not true.
