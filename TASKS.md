# Shiso — Roadmap (Prioritized)

## Tier 1: Do First (Reliability)

- [ ] **Timeout per provider** — cap total wall-clock time per provider scrape, not just per-step. A stuck agent can burn through all 50 steps doing nothing useful ← **HIGH PRIORITY**
- [ ] **Retry with backoff** — if the agent fails on a provider, retry once before marking as failed (currently one-shot)
- [ ] **Session health check** — before scraping, verify the browser profile isn't locked by another Chrome process (`_kill_stale_chrome` exists but is fragile)
- [ ] **Credential validation** — warn on `shiso scrape` if any targeted logins are missing credentials, before launching Chrome

## Tier 2: Observability (User Experience)

- [ ] **Error surfacing** — when a login is flagged `needs_2fa` or `login_failed`, show it prominently in the dashboard with a "retry interactive" button ← **HIGH PRIORITY**
- [ ] **Dashboard sync status polling** — auto-refresh sync status while a run is in progress instead of requiring manual refresh
- [ ] **Run history view** — show past sync runs with metrics (accounts found, steps, failures) per provider in the dashboard

## Tier 3: Data Integrity

- [ ] **Snapshot diffing** — detect when account balances change vs when the scraper just missed them (0 accounts ≠ 0 balance)
- [ ] **Stale data warning** — flag accounts that haven't been successfully scraped in N days
- [ ] **Statement naming & parsing** — downloaded PDFs need consistent naming (`{provider}_{account}_{date}.pdf`) and content extraction (dates, amounts, transaction tables) for dashboard display ← **HIGH PRIORITY**

## Tier 4: Features

- [ ] **Rewards tracking** — credit card points, frequent flyer miles, cashback balances. Either extend `AccountOutput` with rewards fields or a separate `RewardsOutput` schema with history tracking ← **HIGH PRIORITY**
- [ ] **Password manager integration** — Bitwarden CLI (`bw`) for live credential sync instead of CSV re-import. Auto-refresh stale passwords
- [ ] **Bitwarden import** — alternative to Chrome CSV: `bw export --format json` → parse and import

## Tier 5: Quality of Life

- [ ] **`shiso scrape --dry-run`** — show what would be scraped without launching Chrome
- [ ] **Per-provider config in dashboard** — edit `start_url`, `dashboard_url`, enable/disable without touching TOML
- [ ] **Bulk sync from dashboard** — "sync all" exists, add provider-group sync (e.g. all credit cards)

---

## Completed

_Historical log of finished work_
