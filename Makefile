.PHONY: help install dev lint format typecheck test test-cov run migrate clean docker-build docker-up docker-down

# Default target
help:
	@echo "Available targets:"
	@echo "  install     - Install production dependencies"
	@echo "  dev         - Install development dependencies"
	@echo "  lint        - Run ruff linter"
	@echo "  format      - Format code with ruff"
	@echo "  typecheck   - Run mypy type checker"
	@echo "  test        - Run tests"
	@echo "  test-cov    - Run tests with coverage"
	@echo "  check       - Run all checks (lint, typecheck, test)"
	@echo "  run         - Run the application"
	@echo "  migrate     - Run database migrations"
	@echo "  clean       - Clean up cache files"
	@echo "  docker-build - Build Docker image"
	@echo "  docker-up   - Start Docker containers"
	@echo "  docker-down - Stop Docker containers"

# Installation
install:
	uv sync

dev:
	uv sync --all-extras --dev

# Code quality
lint:
	uv run ruff check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy src/

# Testing
test:
	uv run pytest

test-cov:
	uv run pytest --cov=src/axela --cov-report=term-missing --cov-report=html

# Combined check
check: lint typecheck test

# Application
run:
	uv run uvicorn axela.api.app:app --reload --host 0.0.0.0 --port 8000

# Database
migrate:
	uv run alembic upgrade head

migrate-create:
	@read -p "Migration name: " name; \
	uv run alembic revision --autogenerate -m "$$name"

# Cleanup
clean:
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf .coverage
	rm -rf htmlcov
	rm -rf dist
	rm -rf *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Docker
docker-build:
	docker build -t axela .

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f
