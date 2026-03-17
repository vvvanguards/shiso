set shell := ["powershell", "-NoProfile", "-Command"]
root := justfile_directory()

# Shiso — local-first personal finance tracker

default:
    @just --list

# Start API + worker + frontend
start:
    Start-Process powershell -WorkingDirectory '{{root}}' -ArgumentList '-NoExit', '-NoProfile', '-Command', 'uv run python -m shiso.dashboard.main'; Start-Process powershell -WorkingDirectory '{{root}}' -ArgumentList '-NoExit', '-NoProfile', '-Command', 'uv run python -m shiso.scraper.worker'; Set-Location shiso/dashboard/frontend; npm run dev

# API only (port 8002)
api:
    uv run python -m shiso.dashboard.main

# Sync worker only (processes queued sync runs)
worker:
    uv run python -m shiso.scraper.worker

# Frontend only
frontend:
    Set-Location shiso/dashboard/frontend; npm run dev

# Launch Chrome automation profile
chrome:
    uv run python -m shiso.scraper.launch_chrome

# Reset the database
reset-db:
    uv run python -c "from shiso.scraper.database import reset_db; reset_db(); print('DB reset complete')"

# Run scraper for provider(s)
scrape *args:
    uv run python -m shiso.scraper.agent.run --analyst-llm openrouter {{args}}

# Run scraper in auto mode (skip 2FA)
scrape-auto *args:
    uv run python -m shiso.scraper.agent.run --analyst-llm openrouter --auto {{args}}

# Tune scraper hints for a provider
tune provider *args:
    uv run python -m shiso.scraper.agent.smart_tune --analyst-llm openrouter {{provider}} {{args}}

# Check login auth status
auth-status:
    uv run python -m shiso.scraper.agent.auth status

# Interactive login to refresh auth session
auth *args:
    uv run python -m shiso.scraper.agent.auth login --analyst-llm openrouter {{args}}
