<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./frontend/public/assets/openats-logo-white.png">
    <img src="./frontend/public/assets/openats-logo.png" alt="OpenATS logo" width="80">
  </picture>
</p>

<h1 align="center">OpenATS</h1>

<p align="center">
  <strong>An open-source hiring platform to streamline recruitment and hire faster.</strong>
</p>

<p align="center">
  <a href="https://demo.openats.dev"><strong>Live demo</strong></a> ·
  <a href="#key-features"><strong>Features</strong></a> ·
  <a href="#the-stack"><strong>Stack</strong></a> ·
  <a href="#quick-start"><strong>Quick start</strong></a> ·
  <a href="#configuration"><strong>Configuration</strong></a> ·
  <a href="./CONTRIBUTING.md"><strong>Contributing</strong></a>
</p>

<p align="center">
  <img alt="Apache 2.0 licence" src="https://img.shields.io/badge/licence-Apache%202.0-blue.svg">
  <img alt="Next.js" src="https://img.shields.io/badge/frontend-Next.js-black.svg">
  <img alt="FastAPI" src="https://img.shields.io/badge/backend-FastAPI-009688.svg">
  <img alt="Postgres" src="https://img.shields.io/badge/database-Postgres-336791.svg">
</p>

---

## What this is

Recruiting often means juggling spreadsheets, inboxes, and a handful of disconnected
tools. OpenATS brings job creation, candidate tracking, interviews, and hiring
decisions into one workspace teams can set up as their own internal hiring platform.

Many recruitment tools are hard to customize and expensive to scale. OpenATS is a
flexible open-source alternative: use it as a ready-to-go hiring platform, or as the
foundation for building your own internal recruitment system - with full ownership of
the code, the data, and the workflow, instead of adapting your process to fit someone
else's software.

OpenATS provides:

- Full ownership through open-source software
- Flexible and customizable hiring workflows
- A foundation for building internal recruitment platforms
- Reduced dependence on proprietary ATS vendors
- Improved collaboration across hiring teams

## Everything you need to hire better

From job creation to candidate evaluation and hiring decisions, OpenATS provides the
tools your team needs to build a faster, more organized recruitment process.

**Job Management**
Create, organize, and manage job openings with structured requirements, departments,
and hiring workflows.

**Candidate Tracking**
Track applicants through every stage of the hiring process with a clear and
customizable recruitment pipeline.

**Interview Management**
Schedule interviews, collect feedback, and keep everyone aligned throughout the
candidate evaluation process.

**AI Resume Parsing**
Automatically extract and organize candidate information from resumes to save time
and reduce manual work - run as a background job so a slow AI call never blocks a
candidate-facing page.

**Team Collaboration**
Collaborate on hiring decisions with shared feedback, candidate reviews, and
streamlined communication.

**Career Page Builder**
Build a career page that showcases opportunities and attracts the right candidates to
your organization.

## The stack

Two independent packages - not a monorepo, no shared `package.json` or lockfile.

|                     |                                                                                                                                                                                              |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Frontend**        | [Next.js](https://nextjs.org) (App Router) · TypeScript · [Tailwind CSS v4](https://tailwindcss.com) · [shadcn/ui](https://ui.shadcn.com) (`base-vega`) · [hugeicons](https://hugeicons.com) |
| **Backend**         | [FastAPI](https://fastapi.tiangolo.com) (async) · Python · [python-socketio](https://python-socketio.readthedocs.io) for realtime updates                                                   |
| **Data**            | [SQLAlchemy 2.0](https://www.sqlalchemy.org) (async) + Alembic · PostgreSQL (any Postgres, including the one in `docker-compose.yml`)                                                        |
| **Jobs**            | [arq](https://arq-docs.helpmanual.io) on Redis - CV analysis runs as its own worker process, not inline with the API                                                                         |
| **AI**              | [Gemini](https://ai.google.dev) for resume parsing, scoring and candidate summaries                                                                                                          |
| **Auth**            | Self-hosted JWT - bcrypt-hashed passwords, HS256-signed access tokens, roles mapped to `super_admin` / `hiring_manager` / `interviewer`                                                      |
| **Storage**         | Cloudflare R2 (or any S3-compatible bucket) for resumes and attachments                                                                                                                      |
| **Email**           | [Resend](https://resend.com) for candidate and team notifications                                                                                                                            |
| **Package manager** | pnpm for `frontend/`, a standard Python virtualenv for `backend-py/`                                                                                                                          |

### Layout

| Path                                 |                                                                                                                              |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `frontend/`                          | Next.js app · :3000                                                                                                         |
| `backend-py/`                        | FastAPI API · :8080                                                                                                         |
| `backend-py/app/queues/cv_analysis`  | The arq queue, worker, and event bridge for background CV scoring                                                          |
| `backend-py/app/db/models`           | SQLAlchemy models, one file per domain                                                                                     |
| `backend-py/app/alembic/versions`    | Generated migration files - always committed, never hand-edited                                                            |
| `backend/`                           | The original TypeScript/Express implementation, kept for reference during the migration to `backend-py/`                  |
| `e2e/`                               | Playwright end-to-end tests, at the root because they span both packages                                                   |
| `docs/`                              | [Auth setup](./docs-draft/IAM_SETUP.md), [testing guide](./docs-draft/TESTING.md), [road to GA](./docs-draft/GA_ROADMAP.md) |

## Quick start

You need Node.js 22+, Python 3.11+, Docker, and pnpm (`npm install -g pnpm`).

```sh
git clone https://github.com/chamals3n4/OpenATS.git && cd OpenATS

docker compose up -d          # Postgres on :5432, Redis on :6379

cd backend-py
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env          # fill in SECRET_KEY, R2_*, RESEND_*, GEMINI_API_KEY
.venv/bin/alembic upgrade head
.venv/bin/python -m app.db.seed          # required: seeds the 5 default pipeline stages
.venv/bin/python -m app.db.create_admin --email you@example.com --password 'SomeStrongPass1!' \
  --first-name Your --last-name Name    # required: bootstraps your first super_admin user
.venv/bin/uvicorn app.main:asgi_app --reload --port 8080   # API on :8080
```

In a second terminal, the CV analysis worker (its own process, separate from the API):

```sh
cd backend-py
.venv/bin/python -m app.worker_main
```

In a third terminal:

```sh
cd frontend
cp .env.example .env          # fill in OPENATS_API_URL
pnpm install
pnpm dev                      # app on :3000
```

`make setup && make create-admin && make dev` does all of the above for you - see
[CONTRIBUTING.md](./CONTRIBUTING.md) for the full walkthrough.

## Configuration

Each package reads its own `.env` - there's no shared root env file.

**`backend-py/.env`**

| Variable                                             | What it's for                                                       |
| ----------------------------------------------------- | -------------------------------------------------------------------- |
| `DATABASE_URL`                                       | Postgres connection string                                          |
| `REDIS_URL`                                          | Redis, for the CV analysis job queue                                |
| `SECRET_KEY`                                         | Signs and verifies access tokens - required for almost every route  |
| `ENCRYPTION_KEY`                                     | Encrypts stored integration credentials                             |
| `FRONTEND_URL`                                       | Used for CORS and links in outbound emails                          |
| `R2_*`                                               | Cloudflare R2 (or compatible) object storage for uploaded files     |
| `RESEND_*`                                           | Transactional email                                                 |
| `GEMINI_API_KEY`                                     | Powers CV parsing, scoring, and AI summaries                        |
| `GOOGLE_SERVICE_ACCOUNT_JSON` / `GOOGLE_CALENDAR_ID` | Optional - interview scheduling via a Google service account        |

**`frontend/.env`**

| Variable                                  | What it's for                                                  |
| ----------------------------------------- | -------------------------------------------------------------- |
| `OPENATS_API_URL` / `NEXT_PUBLIC_API_URL` | Where the backend is reachable from the server and the browser |

Startup fails fast with a clear message if a required backend variable is missing,
rather than crashing later on the first request that needs it.

## Deploying

TODO

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the full setup walkthrough, branching
rules, and how to open a pull request.

## Licence

[Apache 2.0](./LICENSE).
