# Shiso — AI Agent Guidelines

## Overview

Shiso is a local-first personal automation platform. It uses AI-powered browser automation to scrape financial accounts, extract data from web apps, and present results in a dashboard.

## Development Environment

### Prerequisites
- [uv](https://docs.astral.sh/uv/) — Python package manager
- [Node.js](https://nodejs.org/) — for the dashboard frontend

### Setup
```bash
# Install dependencies
uv sync
cd shiso/dashboard/frontend && npm install

# Copy config and edit with your providers/API keys
cp shiso/scraper/config/scraper.example.toml shiso/scraper/config/scraper.toml

# Launch Chrome automation profile and sign into your sites
uv run shiso chrome

# Import credentials from Chrome password export CSV (via dashboard)
# Upload CSV at http://localhost:8002 → Import Passwords
```

### Running Services
Run each service in a separate terminal:
```bash
# Terminal 1 - API (port 8002)
uv run uvicorn shiso.dashboard.main:app --reload --port 8002

# Terminal 2 - Worker (processes queued syncs, auto-queues scheduled syncs)
uv run python -m shiso.scraper.worker

# Terminal 3 - Frontend (port 5175)
cd shiso/dashboard/frontend && npm run dev
```

### CLI Usage
```bash
uv run shiso scrape             # Scrape all enabled providers
uv run shiso scrape amex        # Scrape one provider
uv run shiso scrape amex -i     # Interactive mode (pause for 2FA)
uv run shiso chrome             # Launch Chrome with automation profile
uv run shiso providers           # List configured providers
uv run shiso auth status         # Check auth status for all logins
uv run shiso auth login amex -i # Interactively log in
uv run shiso tune amex           # Tune scraper hints for a provider
uv run shiso --help              # Full CLI help
```

## Architecture

- **`shiso/cli.py`** — Typer CLI entry point (`shiso` command)
- **`shiso/scraper/`** — Browser-use agent scraper, DB models, sync worker
- **`shiso/scraper/agent/scraper.py`** — Core scraper: builds agent task, runs browser-use Agent, returns `ScrapeResult` with structured metrics
- **`shiso/scraper/services/sync.py`** — Sync lifecycle: creates run records, calls scraper, persists results, runs analyst
- **`shiso/scraper/worker.py`** — Polls DB for queued sync runs, processes one at a time; auto-queues full syncs on schedule
- **`shiso/scraper/alembic/`** — Alembic migrations for schema versioning (see `shiso/scraper/alembic/versions/`)
- **`shiso/scraper/database.py`** — SQLAlchemy SessionLocal factory, tables, and base
- **`shiso/scraper/api.py`** — API facade exposing scraper functionality to dashboard
- **`shiso/scraper/launch_chrome.py`** — Chrome automation profile launcher
- **`shiso/scraper/agent_sessions.py`** — Browser-use Agent session management
- **`shiso/scraper/tools/workflows.py`** — Workflow registry: builtin workflows with DB-backed overrides for runtime-configurable definitions
- **`shiso/scraper/models/`** — SQLAlchemy ORM models (accounts, logins, snapshots, sync_runs, tools)
- **`shiso/dashboard/`** — FastAPI API + Vue 3 / PrimeVue frontend
- **Database**: SQLite at `data/shiso.db` (gitignored)
- **Config**: `shiso/scraper/config/scraper.toml` (gitignored, see `scraper.example.toml`)

## Key Patterns

- **Default is auto mode** — 2FA/CAPTCHA prompts are skipped, login flagged as `needs_2fa`. Use `-i` / `interactive=True` only from CLI when a human is present.
- **Structured metrics, not log parsing** — `scrape_provider` returns `ScrapeResult` with `ScrapeMetrics` populated directly from agent state. Don't parse log strings for metrics.
- **Scraper / Dashboard boundary** — The dashboard imports `shiso.scraper.api as scraper` — a single facade module. Expose new functionality through `shiso/scraper/api.py`.
- **All browser interaction through browser-use Agent** — Never use raw Playwright.
- **Data in DB, styling in client, config in TOML** — Separation of concerns.
- **Dashboard is the primary UI** — CLI is for headless/automation. Steer functionality to the dashboard when possible.
- **Soft-delete for logins** — Deleted logins are marked `is_deleted=true` rather than removed; supports undelete.
- **Migrations over manual schema changes** — Use `alembic revision --autogenerate` to create migrations; never modify the DB schema directly.

## Credentials

- Stored encrypted (Fernet) in `scraper_logins` table
- Imported via Chrome password CSV export (dashboard → Import Passwords)
- Import detects duplicates by `(provider_key, username)` and supports overwriting
- Encryption key at `shiso/scraper/config/.fernet.key` (gitignored, auto-generated)

## Srclight MCP Server

Srclight provides code intelligence for AI agents. It indexes the codebase and exposes MCP tools for symbol search, call graphs, git change intelligence, and semantic search.

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
