# Shiso — AI Agent Guidelines

## Overview

Shiso is a local-first personal automation platform. It uses AI-powered browser automation to scrape financial accounts, extract data from web apps, and present results in a dashboard.

## Development Environment

**All commands use `uv run shiso`. Cross-platform, no Makefile/justfile needed.**

```bash
uv sync                              # Install dependencies
uv run shiso --help                  # CLI help
uv run shiso scrape                  # Run all scrapers (auto mode)
uv run shiso scrape amex -i          # Run one provider (interactive, pauses for 2FA)
uv run shiso chrome                  # Launch Chrome automation profile
uv run shiso providers               # List configured providers
uv run shiso auth status             # Check auth status for all logins
uv run shiso auth login amex -i      # Interactively log in
uv run shiso tune amex               # Tune scraper hints for a provider

# To run services in separate terminals:
#   Terminal 1: uv run uvicorn shiso.dashboard.main:app --reload --port 8002   # API
#   Terminal 2: uv run python -m shiso.scraper.worker                          # Worker
#   Terminal 3: cd shiso/dashboard/frontend && npm run dev                     # Frontend

uv run pytest                        # Run tests
uv run ruff check shiso              # Lint
uv run mypy shiso                    # Type check
```

## Architecture

- **`shiso/cli.py`** — Typer CLI entry point (`shiso` command)
- **`shiso/scraper/`** — Browser-use agent scraper, DB models, sync worker
- **`shiso/scraper/agent/scraper.py`** — Core scraper: builds agent task, runs browser-use Agent, returns `ScrapeResult` with structured metrics
- **`shiso/scraper/services/sync.py`** — Sync lifecycle: creates run records, calls scraper, persists results, runs analyst
- **`shiso/scraper/worker.py`** — Polls DB for queued sync runs, processes one at a time
- **`shiso/scraper/tools/workflows.py`** — Workflow definitions (prompt template + output schema + result key)
- **`shiso/dashboard/`** — FastAPI API + Vue 3 / PrimeVue frontend
- **Database**: SQLite at `data/shiso.db` (gitignored)
- **Config**: `shiso/scraper/config/scraper.toml` (gitignored, see `scraper.example.toml`)

## Browser Profile

Uses a dedicated automation profile at `data/browser-profile/`. Cookies and sessions persist across runs.

- **First run**: `shiso chrome` opens a browser window. Sign into Google (decline sync), then log into provider sites.
- **Subsequent runs**: Already authenticated — agent goes straight to work.
- **One instance at a time**: Chrome locks the profile directory. No parallel scraping.

## Key Patterns

- **Default is auto mode** — 2FA/CAPTCHA prompts are skipped, login flagged as `needs_2fa`. Use `-i` / `interactive=True` only from CLI when a human is present.
- **Structured metrics, not log parsing** — `scrape_provider` returns `ScrapeResult` with `ScrapeMetrics` populated directly from agent state. Don't parse log strings for metrics.
- **Scraper / Dashboard boundary** — The dashboard imports `shiso.scraper.api as scraper` — a single facade module. Expose new functionality through `shiso/scraper/api.py`.
- **All browser interaction through browser-use Agent** — Never use raw Playwright.
- **Data in DB, styling in client, config in TOML** — Separation of concerns.
- **Dashboard is the primary UI** — CLI is for headless/automation. Steer functionality to the dashboard when possible.

## Credentials

- Stored encrypted (Fernet) in `scraper_logins` table
- Imported via Chrome password CSV export (dashboard → Import Passwords)
- Import detects duplicates by `(provider_key, username)` and supports overwriting
- Encryption key at `shiso/scraper/config/.fernet.key` (gitignored, auto-generated)

## Srclight MCP Server

Srclight provides code intelligence for AI agents. It indexes the codebase and exposes 29 MCP tools for symbol search, call graphs, git change intelligence, and semantic search.

**When to use:**

- Use `codebase_map()` at the start of a session to get an overview
- Use `search_symbols(query)` to find functions, classes, or variables by name
- Use `get_callers(name)` / `get_callees(name)` to understand call relationships
- Use `blame_symbol(name)` to see git history for a specific symbol
- Use `hybrid_search(query)` for semantic search (requires embeddings to be configured)

**Key tools:**
- `codebase_map()` — Get project overview (call first each session)
- `search_symbols(query)` — Search symbol names, code, and docs
- `get_callers(name)` / `get_callees(name)` — Relationship graphs
- `blame_symbol(name)` — Git blame for a symbol
- `hybrid_search(query)` — Keyword + semantic search (needs embeddings)
