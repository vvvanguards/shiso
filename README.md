# Shiso

Local-first, privacy-focused personal finance tracker. Uses AI-powered browser automation to scrape financial accounts and presents them in a dashboard.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager
- [just](https://github.com/casey/just) — task runner
- [Node.js](https://nodejs.org/) — for the dashboard frontend

## Setup

```bash
# Install Python dependencies
uv sync

# Copy config and edit with your providers/API keys
cp shiso/scraper/config/scraper.example.toml shiso/scraper/config/scraper.toml

# Create the data directory (gitignored — holds DB, browser profile, statements)
mkdir -p data/browser-profile data/statements

# Initialize the database
just reset-db

# Launch the Chrome automation profile and sign into your financial sites
just chrome
```

## Running

```bash
just start      # API + sync worker + frontend
just scrape     # Run scraper for all providers
just --list     # See all available tasks
```

## Project structure

```
shiso/
  scraper/       # Browser-use agent scraper, DB models, sync worker
  dashboard/     # FastAPI API + Vue 3 / PrimeVue frontend
data/            # Runtime data (gitignored)
  shiso.db       # SQLite database
  browser-profile/  # Chrome automation profile (sessions persist here)
  statements/    # Downloaded account statements
```
