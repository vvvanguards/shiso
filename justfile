# Shiso development commands (Windows PowerShell)

set shell := ["powershell", "-Command"]

# Default: start all services (frontend + worker + API)
dev:
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd shiso/dashboard/frontend; npm run dev"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "uv run python -m shiso.scraper.worker"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "uv run uvicorn shiso.dashboard.main:app --reload --port 8002"

# Start API + worker only (no frontend)
start:
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "uv run python -m shiso.scraper.worker"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "uv run uvicorn shiso.dashboard.main:app --reload --port 8002"

# Worker only
worker:
    uv run python -m shiso.scraper.worker

# Frontend only (needs API running on port 8002)
frontend:
    cd shiso/dashboard/frontend; npm run dev

# Sync all providers (run scrapers in auto mode)
sync:
    uv run shiso scrape

# Run one provider interactively (pauses for 2FA)
scrape target:
    uv run shiso scrape {{target}} -i

# Run all scrapers (auto mode)
scrape-all:
    uv run shiso scrape

# Launch Chrome for manual login
chrome:
    uv run shiso chrome

# List configured providers
providers:
    uv run shiso providers

# Tune scraper hints for a provider
tune provider:
    uv run shiso tune {{provider}}

# Install Python dependencies
install:
    uv sync

# Run tests
test:
    uv run pytest

# Lint
lint:
    uv run ruff check shiso

# Type check
typecheck:
    uv run mypy shiso
