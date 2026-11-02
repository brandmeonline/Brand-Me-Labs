# Copyright (c) Brand.Me, Inc. All rights reserved.
#
# Brand.Me Labs - Monorepo Makefile
# ==================================

.PHONY: help install dev-up dev-down db-migrate db-seed test test-core test-gateway test-chain lint format build-all clean

# Interpreter for the Python suite: BRANDME_PYTHON if set, else the project venv built from
# scripts/python/requirements.lock (same rule as scripts/brandme.mjs).
PYTHON ?= $(or $(BRANDME_PYTHON),.venv/bin/python)

# Default target
help:
	@echo "Brand.Me Labs - Available Commands"
	@echo "===================================="
	@echo ""
	@echo "Development:"
	@echo "  make install      - Install all dependencies"
	@echo "  make dev-up       - Start local development environment"
	@echo "  make dev-down     - Stop local development environment"
	@echo "  make dev-logs     - View development logs"
	@echo ""
	@echo "Database:"
	@echo "  make db-migrate   - Run database migrations"
	@echo "  make db-seed      - Seed database with test data"
	@echo "  make db-reset     - Reset database (drop + migrate + seed)"
	@echo ""
	@echo "Testing & Quality:"
	@echo "  make test         - Foundation gate (pnpm check: drift, types, package/gateway/Python tests, links)"
	@echo "  make test-core    - Full Python suite (tests/), as CI test-core runs it"
	@echo "  make test-gateway - Gateway vitest suites"
	@echo "  make test-chain   - Chain vitest suites"
	@echo "  make lint         - Run linters"
	@echo "  make format       - Format all code"
	@echo "  make type-check   - Run type checkers"
	@echo ""
	@echo "Build:"
	@echo "  make build-all    - Build the five CI images from the repository root, as ci-cd.yml does (publishing is CI-only)"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean        - Clean build artifacts"
	@echo "  make clean-all    - Deep clean (including dependencies)"

# ========================================
# Installation
# ========================================

install: install-gateway install-core install-agents install-chain install-console
	@echo "✓ All dependencies installed"

install-gateway:
	@echo "Installing brandme-gateway dependencies..."
	cd brandme-gateway && pnpm install

install-core:
	@echo "Installing brandme-core dependencies..."
	cd brandme-core && pip install -r requirements.txt

install-agents:
	@echo "Installing brandme-agents dependencies..."
	cd brandme-agents && pip install -r requirements.txt && pip install -r requirements-dev.txt

install-chain:
	@echo "Installing brandme-chain dependencies..."
	cd brandme-chain && pnpm install

install-console:
	@echo "Installing brandme-console dependencies..."
	cd brandme-console && pnpm install

# ========================================
# Development Environment
# ========================================

dev-up:
	@echo "Starting development environment..."
	docker-compose -f docker-compose.dev.yml up -d
	@echo "✓ Development environment started"
	@echo ""
	@echo "Services available at:"
	@echo "  - Gateway:    http://localhost:3000"
	@echo "  - Core:       http://localhost:8000"
	@echo "  - Agents:     http://localhost:8001"
	@echo "  - Chain:      http://localhost:3001"
	@echo "  - Console:    http://localhost:3002"
	@echo "  - PostgreSQL: localhost:5432"
	@echo "  - NATS:       localhost:4222"

dev-down:
	@echo "Stopping development environment..."
	docker-compose -f docker-compose.dev.yml down
	@echo "✓ Development environment stopped"

dev-logs:
	docker-compose -f docker-compose.dev.yml logs -f

# ========================================
# Database Management
# ========================================

db-migrate:
	@echo "Running database migrations..."
	cd brandme-data && python manage.py migrate
	@echo "✓ Migrations completed"

db-seed:
	@echo "Seeding database..."
	cd brandme-data && python manage.py seed
	@echo "✓ Database seeded"

db-reset:
	@echo "⚠️  WARNING: This will drop all database data!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo ""; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		cd brandme-data && python manage.py reset; \
		echo "✓ Database reset completed"; \
	else \
		echo "Aborted"; \
	fi

# ========================================
# Testing
# ========================================

# `make test` is the same gate CI runs (scripts/brandme.mjs check). It reports emulator suites it could not
# run as not_run; BRANDME_REQUIRE_EMULATORS=1 turns those into failures. Removed targets: test-unit/test-int/
# test-agents pointed at brandme-core/tests and brandme-agents/tests, which do not exist, and used --cov
# (pytest-cov is not in scripts/python/requirements.lock); brandme-console has no test script.
test:
	pnpm check

test-core:
	@echo "Running the full Python suite (tests/)..."
	$(PYTHON) -m pytest tests -q --timeout=300 -ra --continue-on-collection-errors

test-gateway:
	@echo "Testing brandme-gateway..."
	pnpm --filter @brandme/gateway exec vitest run

test-chain:
	@echo "Testing brandme-chain..."
	cd brandme-chain && pnpm test

# ========================================
# Code Quality
# ========================================

lint: lint-gateway lint-core lint-agents lint-chain lint-console
	@echo "✓ Linting completed"

lint-gateway:
	cd brandme-gateway && pnpm lint

lint-core:
	cd brandme-core && ruff check src/ && black --check src/

lint-agents:
	cd brandme-agents && ruff check src/ && black --check src/

lint-chain:
	cd brandme-chain && pnpm lint

lint-console:
	cd brandme-console && pnpm lint

format: format-gateway format-core format-agents format-chain format-console
	@echo "✓ Formatting completed"

format-gateway:
	cd brandme-gateway && pnpm format

format-core:
	cd brandme-core && black src/ tests/ && ruff check --fix src/

format-agents:
	cd brandme-agents && black src/ tests/ && ruff check --fix src/

format-chain:
	cd brandme-chain && pnpm format

format-console:
	cd brandme-console && pnpm format

type-check: type-check-gateway type-check-core type-check-agents type-check-chain
	@echo "✓ Type checking completed"

type-check-gateway:
	cd brandme-gateway && pnpm type-check

type-check-core:
	cd brandme-core && mypy src/

type-check-agents:
	cd brandme-agents && mypy src/

type-check-chain:
	cd brandme-chain && pnpm type-check

# ========================================
# Docker Build & Push
# ========================================

build-all: build-gateway build-core build-agents build-chain build-console
	@echo "✓ All images built"

# Root-context builds, the same five images as the ci-cd.yml build-images matrix. Images are tagged :local;
# the registry, project and tags are CI's business (workload identity is the planned path, packet C-checklist).
build-gateway:
	docker build -f brandme-gateway/Dockerfile --build-arg NODE_VERSION=$$(cat .nvmrc) -t brandme-gateway:local .

build-core:
	docker build -f brandme-core/Dockerfile --build-arg NODE_VERSION=$$(cat .nvmrc) -t brandme-core:local .

build-agents:
	docker build -f brandme-agents/Dockerfile --build-arg NODE_VERSION=$$(cat .nvmrc) -t brandme-agents:local .

build-chain:
	docker build -f brandme-chain/Dockerfile --build-arg NODE_VERSION=$$(cat .nvmrc) -t brandme-chain:local .

build-console:
	docker build -f brandme-console/Dockerfile --build-arg NODE_VERSION=$$(cat .nvmrc) -t brandme-console:local .

# ========================================
# Cleanup
# ========================================

clean:
	@echo "Cleaning build artifacts..."
	find . -type d -name "dist" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "build" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "node_modules" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".next" -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Cleaned"

clean-all: clean
	@echo "Deep cleaning (including dependencies)..."
	rm -rf venv/
	rm -rf .venv/
	@echo "✓ Deep clean completed"
