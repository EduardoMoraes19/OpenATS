# OpenATS quickstart
#
#   make setup         install everything, start infra, migrate + seed DB
#   make create-admin   create the first super_admin user (interactive)
#   make dev             start infra + backend + frontend together
#   make worker            start the CV analysis worker (separate process)
#   make infra-up            start docker services only (Postgres, Redis)
#   make infra-down          stop docker services
#   make migrate              run pending database migrations
#   make seed                  seed the default pipeline stages
#   make build                  build the frontend
#   make test                    run backend and frontend tests
#   make clean                    remove node_modules and the Python virtualenv

.PHONY: setup dev worker infra-up infra-down wait-for-db migrate seed create-admin encryption-key secret-key build lint test test-e2e clean

setup:
	@echo "📦 Installing frontend dependencies..."
	pnpm --filter ./frontend install
	@echo ""
	@echo "🐍 Setting up the backend virtualenv (backend-py)..."
	@cd backend-py && python3 -m venv .venv && .venv/bin/pip install -q -e ".[dev]"
	@echo ""
	@if [ ! -f backend-py/.env ] && [ -f backend-py/.env.example ]; then \
		cp backend-py/.env.example backend-py/.env; \
		echo "📄 Created backend-py/.env from .env.example"; \
	fi
	@if [ ! -f frontend/.env ] && [ -f frontend/.env.example ]; then \
		cp frontend/.env.example frontend/.env; \
		echo "📄 Created frontend/.env from .env.example"; \
	fi
	@$(MAKE) encryption-key
	@$(MAKE) secret-key
	@echo ""
	@echo "🐘 Starting Postgres and Redis..."
	@$(MAKE) infra-up
	@$(MAKE) wait-for-db
	@echo ""
	@$(MAKE) migrate
	@$(MAKE) seed
	@echo ""
	@echo "🎉 Setup complete. Run 'make create-admin' to create your first user, then 'make dev' to start OpenATS."
	@echo "   You'll still need to fill in R2_*, RESEND_*, and GEMINI_API_KEY in backend-py/.env by hand."

encryption-key:
	@command -v openssl >/dev/null 2>&1 || { echo "⚠️  openssl not found, skipping ENCRYPTION_KEY generation. Set it manually."; exit 0; }
	@if [ -f backend-py/.env ] && grep -qE '^ENCRYPTION_KEY=[[:space:]]*$$' backend-py/.env; then \
		KEY=$$(openssl rand -hex 32); \
		awk -v key="$$KEY" '{ if ($$0 ~ /^ENCRYPTION_KEY=[[:space:]]*$$/) print "ENCRYPTION_KEY="key; else print $$0 }' backend-py/.env > backend-py/.env.tmp && mv backend-py/.env.tmp backend-py/.env; \
		echo "🔐 Generated ENCRYPTION_KEY in backend-py/.env"; \
	fi

secret-key:
	@command -v openssl >/dev/null 2>&1 || { echo "⚠️  openssl not found, skipping SECRET_KEY generation. Set it manually."; exit 0; }
	@if [ -f backend-py/.env ] && grep -qE '^SECRET_KEY=[[:space:]]*$$' backend-py/.env; then \
		KEY=$$(openssl rand -hex 32); \
		awk -v key="$$KEY" '{ if ($$0 ~ /^SECRET_KEY=[[:space:]]*$$/) print "SECRET_KEY="key; else print $$0 }' backend-py/.env > backend-py/.env.tmp && mv backend-py/.env.tmp backend-py/.env; \
		echo "🔐 Generated SECRET_KEY in backend-py/.env"; \
	fi

infra-up:
	docker compose up -d

infra-down:
	docker compose down

wait-for-db:
	@echo "⏳ Waiting for Postgres to accept connections..."
	@for i in $$(seq 1 30); do \
		docker exec openats-postgres pg_isready -U openats >/dev/null 2>&1 && break; \
		sleep 1; \
	done

migrate:
	@echo "🗄️  Running database migrations..."
	cd backend-py && .venv/bin/alembic upgrade head

seed:
	@echo "🌱 Seeding default pipeline stages..."
	cd backend-py && .venv/bin/python -m app.db.seed

create-admin:
	@echo "👤 Create the first super_admin user"
	@read -p "Email: " email; \
	read -p "First name: " first; \
	read -p "Last name: " last; \
	read -s -p "Password (12+ chars, upper/lower/digit/special): " password; echo ""; \
	cd backend-py && .venv/bin/python -m app.db.create_admin --email "$$email" --password "$$password" --first-name "$$first" --last-name "$$last"

dev: infra-up
	pnpm exec concurrently -n backend,frontend -c blue,green \
		"cd backend-py && .venv/bin/uvicorn app.main:asgi_app --reload --port 8080" \
		"pnpm --filter ./frontend dev"

worker:
	cd backend-py && .venv/bin/python -m app.worker_main

build:
	pnpm --filter ./frontend build

lint:
	pnpm --filter ./frontend lint
	cd backend-py && .venv/bin/ruff check app

clean:
	rm -rf node_modules frontend/node_modules backend-py/.venv

test:
	cd backend-py && .venv/bin/pytest tests/ -q
	pnpm test:frontend

test-e2e:
	pnpm test:e2e
