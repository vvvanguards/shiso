# Plan: SyncType System

## Context

Replaces the `fast_sync: bool` parameter with a DB-driven `SyncType` system.
The `sync_types` lookup table is the source of truth; Python uses a thin `StrEnum`
as a convenience layer. This is designed to integrate with the future tool system.

## Sync Types

| Key | Name | What it does |
|-----|------|-------------|
| `full` | Full Sync | Discovery + enrichment + statements + analyst |
| `balance` | Balance Update | Balance-only scrape for known accounts |
| `statements` | Statements Only | Download statements for known accounts, skip agent scrape |

CLI: `shiso scrape -t <type>` (default: `auto` → resolves based on DB state)

## Auto-Resolution

`resolve_sync_type(login_id)`:
1. If `login.needs_full_sync` → `full`
2. If no accounts exist for the login → `full`
3. Otherwise → `balance`

## DB Schema

### `sync_types` table (new)
```
id, key (unique), name, description, sort_order, active
```
Seeded on init with the three builtin types.

### `scraper_login_sync_runs` — added `sync_type_id` FK → `sync_types.id`

### `scraper_logins` — added columns:
- `needs_full_sync` (bool, default false)
- `last_full_sync_at`, `last_balance_sync_at`, `last_statements_sync_at`

## Files Changed

- `shiso/scraper/models/sync_type.py` — **new**: `SyncTypeRecord`, `SyncType` enum, `resolve_sync_type()`, `get_sync_type_id()`
- `shiso/scraper/models/accounts.py` — new columns on `ScraperLogin` and `ScraperLoginSyncRun`
- `shiso/scraper/database.py` — `_seed_sync_types()`, ALTER TABLE migrations, model import
- `shiso/scraper/services/sync.py` — `SyncRun.sync_type`, auto-resolution in `run_sync()`, per-type tracking in `finalize_sync_run()`
- `shiso/scraper/agent/scraper.py` — all `fast_sync` gating replaced with `sync_type` checks, `_set_needs_full_sync()`, `_load_known_accounts_as_dicts()`, statements-only path
- `shiso/scraper/agent/run.py` — `sync_type: SyncType` parameter plumbing
- `shiso/cli.py` — `--sync-type/-t` option replaces `--fast`
- `shiso/scraper/worker.py` — reads `sync_type_id` from queued run

## Out of Scope
- Parallel provider execution
- API-first approach
- Dashboard UI for selecting sync type (can queue via `sync_type_id` on the run record)
