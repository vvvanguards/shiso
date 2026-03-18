# Shiso — Roadmap

## Reliability

- [ ] **Retry with backoff** — if the agent fails on a provider, retry once before marking as failed (currently one-shot)
- [ ] **Session health check** — before scraping, verify the browser profile isn't locked by another Chrome process (`_kill_stale_chrome` exists but is fragile)
- [ ] **Timeout per provider** — cap total wall-clock time per provider scrape, not just per-step. A stuck agent can burn through all 50 steps doing nothing useful
- [ ] **Credential validation** — warn on `shiso scrape` if any targeted logins are missing credentials, before launching Chrome

## Observability

- [ ] **Dashboard sync status polling** — auto-refresh sync status while a run is in progress instead of requiring manual refresh
- [ ] **Run history view** — show past sync runs with metrics (accounts found, steps, failures) per provider in the dashboard
- [ ] **Error surfacing** — when a login is flagged `needs_2fa` or `login_failed`, show it prominently in the dashboard with a "retry interactive" button

## Data Integrity

- [ ] **Snapshot diffing** — detect when account balances change vs when the scraper just missed them (0 accounts ≠ 0 balance)
- [ ] **Stale data warning** — flag accounts that haven't been successfully scraped in N days

## Quality of Life

- [ ] **`shiso scrape --dry-run`** — show what would be scraped without launching Chrome
- [ ] **Per-provider config in dashboard** — edit `start_url`, `dashboard_url`, enable/disable without touching TOML
- [ ] **Bulk sync from dashboard** — "sync all" exists, add provider-group sync (e.g. all credit cards)
