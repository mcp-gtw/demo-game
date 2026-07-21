.DEFAULT_GOAL := help
.PHONY: help install client client-install client-test lint format test coverage run docker-build docker-run

IMAGE ?= mcp-gateway-demo:latest

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: client ## Install the environment (python dev deps + built client)
	uv sync --extra dev

client-install: ## Install the client toolchain (vite, vitest, phaser)
	npm --prefix client install --no-fund --no-audit

client: client-install ## Build the client bundle into src/app/web/dist
	npm --prefix client run build

client-test: ## Run the client unit tests with the coverage gate
	npm --prefix client run coverage

lint: ## Check linting and formatting
	uv run ruff check .
	uv run ruff format --check .

format: ## Apply formatting and safe lint fixes
	uv run ruff format .
	uv run ruff check --fix .

test: client ## Run the python and client test suites
	uv run pytest -q
	npm --prefix client run test

coverage: client ## Run the python and client suites with their coverage gates
	uv run pytest -q --cov --cov-report=term-missing --cov-report=xml
	npm --prefix client run coverage

run: client ## Serve the game on 127.0.0.1:8000
	uv run python -m app.main

docker-build: ## Build the Docker image (override IMAGE=...)
	docker build -t $(IMAGE) .

docker-run: docker-build ## Build then run the image, serving on 127.0.0.1:8000
	docker run --rm -p 8000:8000 $(IMAGE)
