# Shiso

Local-first personal automation platform. Uses AI-powered browser automation to scrape financial accounts, extract data from web apps, and present results in a dashboard.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager
- [Node.js](https://nodejs.org/) — for the dashboard frontend

## Setup

```bash
# Install Python dependencies
uv sync

# Copy config and edit with your providers/API keys
cp shiso/scraper/config/scraper.example.toml shiso/scraper/config/scraper.toml

# Launch Chrome automation profile and sign into your sites
uv run shiso chrome

# Import credentials from Chrome password export CSV (via dashboard)
uv run shiso start
# Then upload CSV at http://localhost:8002 → Import Passwords
```

## Usage

```bash
uv run shiso start              # API + sync worker + frontend
uv run shiso scrape             # Scrape all enabled providers
uv run shiso scrape amex        # Scrape one provider
uv run shiso scrape amex -i     # Interactive mode (pause for 2FA)
uv run shiso chrome             # Launch Chrome with automation profile
uv run shiso providers          # List configured providers
uv run shiso tune amex          # Tune scraper hints for a provider
uv run shiso --help             # Full CLI help
```

## How it works

1. **First run**: `shiso chrome` opens a dedicated Chrome profile. Log into your financial sites manually (Google account for OAuth, then individual providers). Sessions persist.
2. **Scraping**: `shiso scrape` launches browser-use Agent with the persistent profile. The agent navigates to each provider, extracts account data, and saves snapshots to the DB.
3. **2FA handling**: By default, providers requiring 2FA are skipped and flagged as `needs_2fa`. Use `-i` flag to pause and wait for human input at the terminal.
4. **Dashboard**: `shiso start` runs the API, sync worker, and Vue frontend. Trigger syncs, view accounts, import credentials, and manage providers from the UI.

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
