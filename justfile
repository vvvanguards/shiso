# Shiso development commands
# Install just: https://github.com/casey/just

# Default: show available recipes
default:
    @just --list

# Start API + worker + frontend in dev mode
dev: api worker frontend

# Start API server (port 8002)
api:
    uv run uvicorn shiso.dashboard.main:app --reload --port 8002

# Start scraper worker (processes queued syncs)
worker:
    uv run python -m shiso.scraper.worker

# Start Vite frontend dev server
frontend:
    cd shiso/dashboard/frontend
    npm run dev

# Build frontend for production
build:
    cd shiso/dashboard/frontend
    npm run build

# Run all tests
test:
    uv run pytest

# Run tests with coverage
test-cov:
    uv run pytest --cov=shiso --cov-report=term-missing

# Launch Chrome automation profile
chrome:
    uv run shiso chrome

# List configured providers
providers:
    uv run shiso providers

# Run all scrapers (auto mode)
scrape:
    uv run shiso scrape

# Sync dependencies
sync:
    uv sync

# Install dependencies
install:
    uv sync
    cd shiso/dashboard/frontend
    npm install

# Quick format check
lint:
    uv run ruff check shiso tests