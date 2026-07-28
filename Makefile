# Convenience wrappers around Docker Compose. `make help` lists targets.
COMPOSE      = docker compose
COMPOSE_PROD = docker compose -f docker-compose.yml -f docker-compose.prod.yml

.DEFAULT_GOAL := help

.PHONY: help keygen build up up-prod down down-prod logs logs-prod ps migrate seed stripe-setup shell psql test

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

keygen: ## Print a fresh storage encryption key for .env
	@python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

build: ## Build the web image
	$(COMPOSE) build

up: ## Start locally (db + web on http://localhost:8000)
	$(COMPOSE) up -d --build

up-prod: ## Start in production with Caddy auto-HTTPS
	$(COMPOSE_PROD) up -d --build

down: ## Stop the local stack
	$(COMPOSE) down

down-prod: ## Stop the production stack
	$(COMPOSE_PROD) down

logs: ## Tail local logs
	$(COMPOSE) logs -f --tail=100

logs-prod: ## Tail production logs
	$(COMPOSE_PROD) logs -f --tail=100

ps: ## Show running services
	$(COMPOSE) ps

migrate: ## Run database migrations in the web container
	$(COMPOSE) run --rm web alembic upgrade head

seed: ## Seed demo data (org, agents, a workflow, a document)
	$(COMPOSE) run --rm web python -m app.infrastructure.seed

stripe-setup: ## Create Stripe products & prices (idempotent; needs STRIPE keys in .env)
	$(COMPOSE) run --rm web python -m app.infrastructure.billing.setup_stripe

shell: ## Open a shell in the web container
	$(COMPOSE) exec web sh

psql: ## Open psql against the database
	$(COMPOSE) exec db psql -U $${POSTGRES_USER:-orchestract} -d $${POSTGRES_DB:-orchestract}

test: ## Run the test suite locally (uv)
	uv run pytest
