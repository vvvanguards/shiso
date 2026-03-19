# Shiso

Local-first personal automation platform. Uses AI-powered browser automation to scrape financial accounts, extract data from web apps, and present results in a dashboard.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager
- [Node.js](https://nodejs.org/) — for the dashboard frontend

## Setup

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

## Development

Run each service in a separate terminal:

```powershell
# Terminal 1 - API (port 8002)
uv run uvicorn shiso.dashboard.main:app --reload --port 8002

# Terminal 2 - Worker (processes queued syncs)
uv run python -m shiso.scraper.worker

# Terminal 3 - Frontend (port 5175)
cd shiso/dashboard/frontend && npm run dev
```

## Usage

```bash
uv run shiso scrape             # Scrape all enabled providers
uv run shiso scrape amex        # Scrape one provider
uv run shiso scrape amex -i     # Interactive mode (pause for 2FA)
uv run shiso chrome             # Launch Chrome with automation profile
uv run shiso providers          # List configured providers
uv run shiso auth status        # Check auth status for all logins
uv run shiso auth login amex -i # Interactively log in
uv run shiso tune amex          # Tune scraper hints for a provider
uv run shiso --help             # Full CLI help
```

## How it works

1. **First run**: `shiso chrome` opens a dedicated Chrome profile. Log into your financial sites manually (Google account for OAuth, then individual providers). Sessions persist.
2. **Scraping**: `shiso scrape` launches browser-use Agent with the persistent profile. The agent navigates to each provider, extracts account data, and saves snapshots to the DB.
3. **2FA handling**: By default, providers requiring 2FA are skipped and flagged as `needs_2fa`. Use `-i` flag to pause and wait for human input at the terminal.
4. **Dashboard**: Run the three services (API, worker, frontend) to trigger syncs, view accounts, import credentials, and manage providers from the UI.

## Project structure

```
shiso/
  cli.py           # Typer CLI entry point
  scraper/         # Browser-use agent, DB models, sync worker
    agent/         # Agent scraper, analyst, tuning
    config/        # scraper.toml, accounts.json, provider hints
    services/      # Sync, crypto, password import
    tools/         # Workflow definitions (financial, leads, etc.)
  dashboard/       # FastAPI API + Vue 3 / PrimeVue frontend
data/              # Runtime data (gitignored)
  shiso.db         # SQLite database
  browser-profile/ # Chrome automation profile
  statements/      # Downloaded account statements
```
