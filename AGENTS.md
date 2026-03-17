# Shiso — AI Agent Guidelines

## Overview

Shiso is a local-first, privacy-focused personal finance tracker. It uses AI-powered browser automation to scrape financial accounts and presents them in a dashboard.

## Development Environment

**Use uv for Python dependencies. Use just for tasks.**

```bash
uv sync                   # Install dependencies
just --list               # List available tasks
just start                # Start API + worker + frontend
just scrape               # Run scraper
```

## Architecture

- **`shiso/scraper/`** — Browser-use agent scraper, DB models, sync worker
- **`shiso/dashboard/`** — FastAPI API + Vue 3 / PrimeVue frontend
- **Database**: SQLite at `data/shiso.db` (gitignored)
- **Config**: `shiso/scraper/config/scraper.toml` (gitignored, see `scraper.example.toml`)

## Scraper / Dashboard Boundary

The dashboard imports `shiso.scraper.api as scraper` — a single facade module. When adding new scraper functionality that the dashboard needs, expose it through `shiso/scraper/api.py` rather than having the dashboard import deep internals.

## Best Practices

1. **Read existing code first** — Understand the structure before making changes
2. **Follow existing patterns** — Match the style of existing code
3. **All browser interaction must go through browser-use Agent** — Never use raw Playwright
4. **Data in DB, styling in client, config in TOML** — Separation of concerns
