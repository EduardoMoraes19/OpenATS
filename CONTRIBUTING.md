## Contributing to OpenATS

> 🔑 Setting up authentication? See [docs-draft/IAM_SETUP.md](docs-draft/IAM_SETUP.md) for the full auth setup guide.

- [Prerequisites](#prerequisites)
- [Tech Stack](#tech-stack)
- [Quick Start (Recommended)](#quick-start-recommended)
- [Manual Setup](#manual-setup)
  - [Fork and Clone](#1-fork-and-clone)
  - [Add Upstream Remote](#2-add-upstream-remote)
  - [Install Frontend Dependencies](#3-install-frontend-dependencies)
  - [Set up the Backend Virtualenv](#4-set-up-the-backend-virtualenv)
- [Database Setup](#database-setup)
  - [Start Postgres and Redis with Docker](#1-start-postgres-and-redis-with-docker)
  - [Setup environment variables](#2-setup-environment-variables)
  - [Run database migrations](#3-run-database-migrations)
  - [Seed the database](#4-seed-the-database)
  - [Create your first admin user](#5-create-your-first-admin-user)
- [Running the Project](#running-the-project)
  - [Frontend](#frontend)
  - [Backend](#backend)
  - [Backend Worker](#backend-worker)
- [Testing](#testing)
- [Working on a Task](#working-on-a-task)
  - [Before you start ANYTHING](#before-you-start-anything)
  - [Create a new branch for your task](#create-a-new-branch-for-your-task)
  - [Work on your code, then commit](#work-on-your-code-then-commit)
  - [Push your branch](#push-your-branch)
  - [Create Pull Request on GitHub](#create-pull-request-on-github)
- [Important Rules](#important-rules)

## Prerequisites

Before you start, make sure you have these installed:

- Node.js (version 22 or higher), [download here](https://nodejs.org/)
- Python (version 3.11 or higher), [download here](https://www.python.org/downloads/)
- Git, [download here](https://git-scm.com/)
- Docker, [download here](https://docs.docker.com/get-docker/) (runs Postgres, Redis, and MinIO locally, no manual install needed)
- Make (usually preinstalled on macOS and Linux, on Windows use WSL)
- A code editor (VS Code recommended)

Check if you have them:

```bash
node --version
python3 --version
git --version
docker --version
make --version
```

## Tech Stack

**Frontend (web)**

- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui (for UI components)

**Backend (api)**

- FastAPI (async)
- Python
- PostgreSQL (database)
- Redis (job queue, via arq)
- SQLAlchemy 2.0 + Alembic (database ORM and migrations)
- Self-hosted JWT auth (bcrypt password hashing, HS256 tokens)

**Package Manager:** pnpm for `frontend/`; a standard Python virtualenv (`pip`) for `backend-py/`

## Quick Start (Recommended)

If you have `make` installed, this is the fastest way to get running:

```bash
git clone https://github.com/chamals3n4/OpenATS.git
cd OpenATS
make setup
make create-admin
make dev
```

`make setup` does all of this for you, in order:

1. Installs `frontend/`'s dependencies via pnpm
2. Creates a Python virtualenv at `backend-py/.venv` and installs the backend there
3. Copies `backend-py/.env.example` and `frontend/.env.example` into real `.env` files, if they don't exist yet
4. Generates a random `ENCRYPTION_KEY` and `SECRET_KEY` for you, if they're still blank
5. Starts Postgres, Redis, and MinIO via Docker
6. Runs database migrations and seeds the default pipeline stages

`make create-admin` then walks you through creating your first user (email, name,
and password) - there's no sign-up page, so this is the only way to get your first
login.

`make dev` starts the backend and frontend together.

Object storage (`R2_*`) already points at the local MinIO container `make setup` starts for you, so file uploads (resumes, company logos) work out of the box - no Cloudflare account needed for local dev. You'll still need to fill in a couple of provider credentials by hand afterward, since these are personal secrets nobody can generate for you: Resend and Gemini.

Prefer to see every step yourself, or something in `make setup` isn't working? The full manual walkthrough is below, and it's also the fallback if you ever need to debug a step individually.

## Manual Setup

### 1. Fork and Clone

Fork the repository on GitHub first, then:

```bash
git clone https://github.com/chamals3n4/OpenATS.git
cd OpenATS
```

### 2. Add Upstream Remote

```bash
git remote add upstream https://github.com/chamals3n4/OpenATS.git
git remote -v  # verify you have both origin and upstream
```

### 3. Install Frontend Dependencies

```bash
npm install -g pnpm
cd frontend
pnpm install
cd ..
```

### 4. Set up the Backend Virtualenv

```bash
cd backend-py
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cd ..
```

## Database Setup

### 1. Start Postgres and Redis with Docker

The backend needs a PostgreSQL database, a Redis instance (used for the CV analysis job queue via arq), and S3-compatible object storage for file uploads (resumes, company logos). A `docker-compose.yml` is provided at the repo root, so you don't need to install or configure any of them manually:

```bash
docker compose up -d
```

This starts:

- **Postgres** on `localhost:5432` (user: `openats`, password: `openats`, db: `openats`)
- **Redis** on `localhost:6379`
- **MinIO** on `localhost:9000` (S3 API) and `localhost:9001` (web console, login `openats`/`openats12345`) - a `minio-init` container also creates the `openats` bucket automatically and exits; `backend-py/.env.example` already points `R2_*` at it, so uploads work locally with no Cloudflare R2 account. Production swaps those same `R2_*` variables for real Cloudflare R2 credentials (or a self-hosted MinIO with TLS) - the app code doesn't change either way.

Check they're running:

```bash
docker compose ps
```

Stop them when you're done for the day (data is preserved):

```bash
docker compose stop
```

Remove the containers (data volumes are preserved unless you add `-v`):

```bash
docker compose down
```

### 2. Setup environment variables

Inside `frontend`, copy the example env file:

```bash
cd frontend
cp .env.example .env
cd ..
```

Inside `backend-py`, copy the example env file:

```bash
cd backend-py
cp .env.example .env
cd ..
```

If you're using the Docker containers from step 1, `DATABASE_URL` and `REDIS_URL` in `backend-py/.env` are already filled in correctly by default:

```bash
DATABASE_URL=postgresql+asyncpg://openats:openats@localhost:5432/openats
REDIS_URL=redis://localhost:6379
```

Generate a `SECRET_KEY` (signs and verifies access tokens) and an `ENCRYPTION_KEY`
(encrypts stored integration credentials) if they're blank:

```bash
openssl rand -hex 32
```

Put the value in `backend-py/.env` for each. `make setup` does this for you
automatically.

### 3. Run database migrations

```bash
make migrate
```

### 4. Seed the database

This inserts the default hiring pipeline stages the app needs to work:

```bash
make seed
```

### 5. Create your first admin user

There's no sign-up flow: create the first `super_admin` user directly, either
interactively via:

```bash
make create-admin
```

or directly:

```bash
cd backend-py
.venv/bin/python -m app.db.create_admin --email you@example.com \
  --password 'SomeStrongPass1!' --first-name Your --last-name Name
```

You only need steps 3 to 5 **once**, when setting up for the first time.

> ⚠️ If you pull changes that include schema changes, run `make migrate` again to keep your database in sync.

## Running the Project

The fastest way is one command from the repo root. It starts Postgres and Redis, then the backend and frontend together:

```bash
make dev
```

Frontend runs on `http://localhost:3000`, backend on `http://localhost:8080`.

### Frontend

```bash
cd frontend
pnpm dev
```

### Backend

```bash
cd backend-py
.venv/bin/uvicorn app.main:asgi_app --reload --port 8080
```

### Backend Worker

CV analysis runs as a background job queue and needs its own process, separate from the API server:

```bash
make worker
```

or directly:

```bash
cd backend-py
.venv/bin/python -m app.worker_main
```

## Testing

Full guide: [docs-draft/TESTING.md](docs-draft/TESTING.md).

There are three kinds of tests:

- **Unit tests** check a single function with no database.
- **Integration tests** check API routes against a real database.
- **End-to-end tests** open a real browser and use the app like a person would.

### First time only

Start the test database and apply the schema to it:

```bash
docker compose -f docker-compose.test.yml up -d
cd backend-py
DATABASE_URL=postgresql+asyncpg://openats:openats@localhost:5433/openats_test .venv/bin/alembic upgrade head
cd ..
```

> ⚠️ Note the port is **5433**, not 5432. Tests use their own database so they never touch your development data.

### Running tests

```bash
make test        # backend (pytest) and frontend (vitest) unit and integration tests
pnpm test:e2e     # end-to-end tests (stop `make dev` first)
```

Backend-only checks:

```bash
cd backend-py
.venv/bin/pytest tests/ -q
.venv/bin/ruff check app
.venv/bin/mypy app
```

Please run `make test` before opening a pull request.

## Working on a Task

### Before you start ANYTHING:

```bash
git checkout main
git pull upstream main
git push origin main
```

### Create a new branch for your task:

```bash
git checkout -b feature/task-name
# or
git checkout -b fix/bug-name
```

### Work on your code, then commit:

```bash
git add .
git commit -m "brief description of what you did"
```

### Push your branch:

```bash
git push origin feature/task-name
```

### Create Pull Request on GitHub

Go to GitHub and create a PR from your branch to the main repository.

## Important Rules

- NEVER push directly to main
- ALWAYS pull from upstream before starting work
- Create a NEW branch for each task
- Keep commits small and focused
- Run `make test` before pushing
- If you modify the database schema, always run `make migrate` and commit the generated Alembic migration file along with your schema changes

---

Happy coding!
