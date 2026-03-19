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
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "uv run python -m shiso.scraper.worker"

# Frontend only (needs API running on port 8002)
frontend:
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd shiso/dashboard/frontend; npm run dev"

# Stop all services (API, worker, frontend)
stop:
    Get-NetTCPConnection -LocalPort 8002 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    Get-NetTCPConnection -LocalPort 5175 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    Get-Process -Name "uvicorn" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped all shiso services"

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
