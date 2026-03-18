# Shiso — AI Agent Guidelines

## Overview

Shiso is a local-first personal automation platform. It uses AI-powered browser automation to scrape financial accounts, extract data from web apps, and present results in a dashboard.

## Development Environment

**Use uv for Python dependencies. CLI is `shiso`.**

```bash
uv sync                         # Install dependencies
uv run shiso --help             # CLI help
uv run shiso scrape             # Run all scrapers (auto mode)
uv run shiso scrape amex -i     # Run one provider (interactive, pauses for 2FA)
uv run shiso chrome             # Launch Chrome automation profile
uv run shiso providers          # List configured providers
uv run shiso start              # Start API + worker + frontend
uv run shiso tune amex          # Tune scraper hints for a provider
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
