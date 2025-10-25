# Copyright (c) Brand.Me, Inc. All rights reserved.
#
# Brand.Me Labs - Monorepo Makefile
# ==================================

.PHONY: help install dev-up dev-down db-migrate db-seed test lint format build-all push-all clean

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
	@echo "  make test         - Run all tests"
	@echo "  make test-unit    - Run unit tests only"
	@echo "  make test-int     - Run integration tests"
	@echo "  make lint         - Run linters"
	@echo "  make format       - Format all code"
	@echo "  make type-check   - Run type checkers"
	@echo ""
	@echo "Build & Deploy:"
	@echo "  make build-all    - Build all Docker images"
	@echo "  make push-all     - Push all Docker images to registry"
	@echo "  make deploy-dev   - Deploy to development environment"
	@echo "  make deploy-prod  - Deploy to production environment"
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
	cd brandme-core && pip install -r requirements.txt && pip install -r requirements-dev.txt

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

test: test-gateway test-core test-agents test-chain test-console
	@echo "✓ All tests passed"

test-unit:
	@echo "Running unit tests..."
	cd brandme-core && pytest tests/unit -v
	cd brandme-agents && pytest tests/unit -v

test-int:
	@echo "Running integration tests..."
	cd brandme-core && pytest tests/integration -v
	cd brandme-agents && pytest tests/integration -v

test-gateway:
	@echo "Testing brandme-gateway..."
	cd brandme-gateway && pnpm test

test-core:
	@echo "Testing brandme-core..."
	cd brandme-core && pytest tests/ -v --cov=src --cov-report=html

test-agents:
	@echo "Testing brandme-agents..."
	cd brandme-agents && pytest tests/ -v --cov=src --cov-report=html

test-chain:
	@echo "Testing brandme-chain..."
	cd brandme-chain && pnpm test

test-console:
	@echo "Testing brandme-console..."
	cd brandme-console && pnpm test

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

build-gateway:
	@echo "Building brandme-gateway..."
	docker build -t gcr.io/brandme/gateway:latest ./brandme-gateway

build-core:
	@echo "Building brandme-core..."
	docker build -t gcr.io/brandme/core-brain:latest ./brandme-core/brain
	docker build -t gcr.io/brandme/core-policy:latest ./brandme-core/policy
	docker build -t gcr.io/brandme/core-orchestrator:latest ./brandme-core/orchestrator

build-agents:
	@echo "Building brandme-agents..."
	docker build -t gcr.io/brandme/agent-identity:latest ./brandme-agents/identity
	docker build -t gcr.io/brandme/agent-knowledge:latest ./brandme-agents/knowledge
	docker build -t gcr.io/brandme/agent-compliance:latest ./brandme-agents/compliance

build-chain:
	@echo "Building brandme-chain..."
	docker build -t gcr.io/brandme/chain:latest ./brandme-chain

build-console:
	@echo "Building brandme-console..."
	docker build -t gcr.io/brandme/console:latest ./brandme-console

push-all: push-gateway push-core push-agents push-chain push-console
	@echo "✓ All images pushed"

push-gateway:
	docker push gcr.io/brandme/gateway:latest

push-core:
	docker push gcr.io/brandme/core-brain:latest
	docker push gcr.io/brandme/core-policy:latest
	docker push gcr.io/brandme/core-orchestrator:latest

push-agents:
	docker push gcr.io/brandme/agent-identity:latest
	docker push gcr.io/brandme/agent-knowledge:latest
	docker push gcr.io/brandme/agent-compliance:latest

push-chain:
	docker push gcr.io/brandme/chain:latest

push-console:
	docker push gcr.io/brandme/console:latest

# ========================================
# Deployment
# ========================================

deploy-dev:
	@echo "Deploying to development environment..."
	cd brandme-infra/helm && \
	helm upgrade --install brandme ./brandme-umbrella \
		--values values-dev.yaml \
		--namespace brandme-dev \
		--create-namespace
	@echo "✓ Deployed to development"

deploy-prod:
	@echo "⚠️  WARNING: Deploying to PRODUCTION!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo ""; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		cd brandme-infra/helm && \
		helm upgrade --install brandme ./brandme-umbrella \
			--values values-prod.yaml \
			--namespace brandme \
			--create-namespace; \
		echo "✓ Deployed to production"; \
	else \
		echo "Aborted"; \
	fi

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

# ========================================
# Infrastructure
# ========================================

infra-init:
	@echo "Initializing Terraform..."
	cd brandme-infra/terraform && terraform init
	@echo "✓ Terraform initialized"

infra-plan:
	@echo "Planning infrastructure changes..."
	cd brandme-infra/terraform && terraform plan

infra-apply:
	@echo "Applying infrastructure changes..."
	cd brandme-infra/terraform && terraform apply

infra-destroy:
	@echo "⚠️  WARNING: This will destroy ALL infrastructure!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo ""; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		cd brandme-infra/terraform && terraform destroy; \
		echo "✓ Infrastructure destroyed"; \
	else \
		echo "Aborted"; \
	fi
