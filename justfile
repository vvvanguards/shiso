# Shiso development commands
# Install: https://github.com/casey/just

set windows-shell := ["cmd.exe", "/C"]

# Show available recipes
default:
    @just --list

# Start all services (API + worker + frontend)
dev:
    start /B uv run uvicorn shiso.dashboard.main:app --reload --port 8002
    start /B uv run python -m shiso.scraper.worker
    npm run dev --prefix shiso/dashboard/frontend

# Start API server (port 8002)
api:
    uv run uvicorn shiso.dashboard.main:app --reload --port 8002

# Start scraper worker
worker:
    uv run python -m shiso.scraper.worker

# Start Vite frontend
frontend:
    npm run dev --prefix shiso/dashboard/frontend

# Build frontend
build:
    npm run build --prefix shiso/dashboard/frontend

# Run tests
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

# Run scrapers (auto mode)
scrape:
    uv run shiso scrape

# Sync Python dependencies
sync:
    uv sync

# Install all dependencies
install:
    uv sync
    npm install --prefix shiso/dashboard/frontend

# Lint check
lint:
    uv run ruff check shiso tests