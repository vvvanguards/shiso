# Shiso — AI Agent Guidelines

## Overview

Shiso is a local-first personal automation platform. It uses AI-powered browser automation to scrape financial accounts, extract data from web apps, and present results in a dashboard.

## Development Environment

**Use uv for Python dependencies. CLI is `shiso`.**

```bash
uv sync                    # Install dependencies
uv run shiso --help        # CLI help
uv run shiso scrape        # Run all scrapers
uv run shiso scrape amex   # Run one provider
uv run shiso chrome        # Launch Chrome with CDP
uv run shiso providers     # List configured providers
uv run shiso start         # Start API + worker + frontend
```

## Architecture

- **`shiso/cli.py`** — Typer CLI entry point (`shiso` command)
- **`shiso/scraper/`** — Browser-use agent scraper, DB models, sync worker
- **`shiso/dashboard/`** — FastAPI API + Vue 3 / PrimeVue frontend
- **Database**: SQLite at `data/shiso.db` (gitignored)
- **Config**: `shiso/scraper/config/scraper.toml` (gitignored, see `scraper.example.toml`)

## Browser Profile

Uses a dedicated automation profile at `data/browser-profile/`. Cookies and sessions persist across runs.

- **First run**: `shiso chrome` opens a browser window. Log into sites manually.
- **Subsequent runs**: Already authenticated — agent goes straight to work.

## Scraper / Dashboard Boundary

The dashboard imports `shiso.scraper.api as scraper` — a single facade module. When adding new scraper functionality that the dashboard needs, expose it through `shiso/scraper/api.py` rather than having the dashboard import deep internals.

## Best Practices

1. **Read existing code first** — Understand the structure before making changes
2. **Follow existing patterns** — Match the style of existing code
3. **All browser interaction must go through browser-use Agent** — Never use raw Playwright
4. **Data in DB, styling in client, config in TOML** — Separation of concerns
