.DEFAULT_GOAL := help

.PHONY: start stop build logs ps restart clean help

start: ## Start all services (db + api), building images if needed
	docker compose up --build -d

stop: ## Stop all services and remove containers (data volume is kept)
	docker compose down

build: ## Rebuild images without starting containers
	docker compose build

logs: ## Follow logs from all services
	docker compose logs -f

ps: ## Show status of running services
	docker compose ps

restart: stop start ## Stop then start all services

clean: ## Stop all services and delete the Postgres data volume too
	docker compose down -v

lint: ## Lints the project for styling and formating
	uv sync --extra dev
	./scripts/lint.sh

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'
