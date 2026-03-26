# Shiso — Roadmap

**Mission:** Local-first financial aggregation via browser scraping. One thing, done extremely well.

**What we are:** AI-powered browser automation for financial accounts. NOT a general-purpose scraper. NOT going broad. NOT Plaid. We do what Plaid can't: promo APRs, rewards balances, statement PDFs, any institution.

**What we are NOT:** Generic automation, Zillow leads, utility bill scraping, extensible tool platform.

---

## Tier 1: Make It Bulletproof

### Reliability
- [ ] **Retry with backoff** — if a provider fails, retry once before marking failed. Currently one-shot.
- [ ] **Session health check** — verify Chrome profile isn't locked before scraping. Current `_kill_stale_chrome` is fragile.
- [ ] **Credential validation** — warn before scraping if any targeted logins are missing credentials.

### Data Integrity
- [ ] **Snapshot diffing** — distinguish "scraper missed accounts" (0 returned) from "balance is actually 0". Prevents false zeros from looking like real data.
- [ ] **Stale data warning** — flag accounts that haven't been successfully scraped in N days.

---

## Tier 2: Speed & Optimization

### Already Done
- **SyncType system** — design spec exists (`PLAN-fast-sync.md`). `fast_sync: bool` needs to be replaced with proper `sync_types` table + enum. This unblocks per-type scheduling.

### In Flight
- **Rewards as assets** — PRs #5 and #6 merged. `RewardsSection.vue`, migration, `current_balance` on `RewardsProgram`, and scrape integration still pending.

### Not Started
- [ ] **Implement SyncType system** — `balance` (fast, known accounts) vs `full` (discovery + enrichment + statements) vs `statements_only`. DB-driven, not bool.
- [ ] **Parallel provider sync** — worker processes one provider at a time. Parallel execution would be a significant speed win.
- [ ] **Session reuse / warm start** — reuse Chrome session across providers instead of launching fresh each time.

---

## Tier 3: Observability

### Already Done
- **Error surfacing in dashboard** — `needs_2fa` / `login_failed` flags surface in dashboard (multiple rounds of improvement).

### Not Started
- [ ] **Dashboard sync status polling** — auto-refresh while a run is in progress instead of manual refresh.
- [ ] **Run history view** — past sync runs with metrics (accounts found, steps, failures) per provider.

---

## Tier 4: UI/UX — Simplify

- [ ] **Per-provider config in dashboard** — edit `start_url`, `dashboard_url`, enable/disable without touching TOML.
- [ ] **Bulk sync by group** — sync all credit cards, all banks — not just "sync all" and not individual.
- [ ] **`shiso scrape --dry-run`** — show what would be scraped without launching Chrome.

---

## Tier 5: Nice to Have

- [ ] **Bitwarden import** — `bw export --format json` → parse and import, as alternative to Chrome CSV.
- [ ] **Statement content extraction** — PDFs are downloaded per-account but content (transactions, amounts, dates) isn't parsed into structured data for the dashboard.
- [ ] **Rewards tracking** — partially done via rewards-as-assets. Scrape integration to update `current_balance` on each run is still needed.

---

## Scope

**In scope (financial):** Checking, savings, credit cards, brokerage, utilities (electric, water, gas), rewards programs.

**Out of scope:**
- ~~Zillow Rental Manager / real estate~~ — not financial
- ~~Extensible tool / workflow registry~~ — over-engineered for the actual use case
- ~~Plaid integration~~ — loses promo APRs, rewards details, statement PDFs, unsupported institutions. We do what Plaid can't.
- ~~General-purpose browser automation platform~~ — scope creep

---

## Completed

- **Timeout per provider** — wall-clock cap per provider, graceful kill, timeout status in metrics (2026-03-17)
- **Rewards tracking** — schema, API endpoints, dashboard display, rewards-as-assets design (2026-03-24)
- **Soft-delete for logins** — `is_deleted=true` with undelete support
- **Alembic migrations** — DB schema versioning
- **Balance-only fast-sync** — skip statements for known accounts
- **Per-account statement download** — one PDF per account, named consistently
- **Adaptive scraper tuning** — typed analyst models for self-tuning
- **LLM-based 2FA detection** — assess auth state before retry
- **Browser-use agent history** — saved to disk per scrape run
- **Sectioned sidebar** — grouped navigation
- **Auto-sync scheduling** — worker auto-queues full syncs on interval
- **`account_number` as dedup key** — stable identity across renames
