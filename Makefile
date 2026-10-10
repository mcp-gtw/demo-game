.DEFAULT_GOAL := help
.PHONY: help install client client-install client-test lint format test coverage run docker-build docker-run oauth-smoke embedded-smoke proxy-smoke build

IMAGE ?= mcp-gateway-demo:latest

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: client ## Install the environment (python dev deps + built client)
	uv sync --extra dev --locked

client-install: ## Install the client toolchain (vite, vitest, phaser)
	npm --prefix client ci --no-fund --no-audit

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

docker-run: docker-build ## Build then run the image, serving on 127.0.0.1:8000
	docker run --rm -p 8000:8000 $(IMAGE)

docker-build: ## Build the game with the gateway feature wheel
	mkdir -p artifacts
	uv --directory ../mcp-gtw build --wheel --out-dir ../mcp-gtw-demo-game/artifacts
	docker build -t $(IMAGE) .

oauth-smoke: client ## Run the local HTTPS Token/OAuth browser integration
	uv run python tests/e2e/run.py

proxy-smoke: ## Test the built mcp-gtw-game:oauth image through local nginx HTTPS
	uv run python tests/e2e/proxy.py

embedded-smoke: client ## Exercise the production embedded OAuth server locally
	uv run python tests/e2e/embedded.py

build: client ## Build wheel and sdist with the required bundled frontend
	uv build
