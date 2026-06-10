DC  ?= docker compose
NPM ?= npm
WEB_DIR ?= web

# ── Dev ───────────────────────────────────────────────────────────────────────

dev: ## Start all services + migrate (no rebuild)
	$(DC) up -d
	$(MAKE) migrate

dev-build: ## Build images, start all services + migrate
	$(DC) up --build -d
	$(MAKE) migrate

down: ## Stop containers (volumes preserved)
	$(DC) down

reset: ## Wipe DB + rebuild images + migrate (destructive!)
	$(DC) down -v --remove-orphans
	$(MAKE) dev-build

# ── Migrations ────────────────────────────────────────────────────────────────

migrate: ## Apply all pending Alembic migrations
	$(DC) --profile migrate run --rm migrate

migrate-rebuild: ## Rebuild migrate image + apply all pending migrations
	$(DC) --profile migrate build migrate
	$(MAKE) migrate

migrate-create: ## Create new migration: make migrate-create MSG="describe change"
	$(DC) --profile migrate run --rm --entrypoint "" migrate \
		alembic revision --autogenerate -m "$(MSG)"

# ── Debug ─────────────────────────────────────────────────────────────────────

logs: ## Tail all logs
	$(DC) logs -f

shell: ## Bash inside api container
	$(DC) exec api /bin/bash

db-shell: ## psql inside postgres container
	$(DC) exec -it postgres sh -c 'psql -U "$$POSTGRES_USER" "$$POSTGRES_DB"'

# ── Lint / QA ─────────────────────────────────────────────────────────────────

lint: ## Run all pre-commit hooks on all files
	uv run pre-commit run --all-files

lint-fast: ## Run only ruff (format + lint) on all files
	uv run ruff check --fix .
	uv run ruff format .

# ── Demo seed ─────────────────────────────────────────────────────────────────

seed-demo: ## Seed demo persona via DB (DATABASE_URL required)
	uv run python -m scripts.seed_demo --persona $(or $(PERSONA),meiko_tokyo)

seed-demo-reset: ## Delete demo persona from DB (PERSONA=...; DATABASE_URL required)
	uv run python -m scripts.seed_demo --persona $(or $(PERSONA),meiko_tokyo) --reset
