# Rewards as Assets — Design Spec

## Overview

Rewards programs (frequent flyer miles, hotel points, credit card rewards) are integrated as a sub-section of the Assets view, similar to how Bills are a sub-section of Liabilities. The monetary value of rewards is included in the asset total.

**Key changes:**
- `RewardsProgram` model updated: `scraper_login_id` becomes required, `financial_account_id` becomes optional, `membership_id` field added
- `current_balance` added to `RewardsProgram` for fast access (historical balance tracking via existing `RewardsBalance` table)
- New `RewardsSection` component added to the frontend as a sub-section of Assets
- Rewards monetary value flows into the asset summary total
- Existing Rewards panel (add/edit programs) remains but is scoped to the Assets nav tree

---

## Data Model

### `RewardsProgram` (modified)

| Field | Change | Notes |
|-------|--------|-------|
| `id` | — | existing |
| `scraper_login_id` | **Now required** | Where you log in to manage the program |
| `financial_account_id` | **Now nullable** | Optional link to a card account (e.g., Amex Platinum → Delta SkyMiles) |
| `program_name` | — | "Chase Ultimate Rewards", "Hilton Honors" |
| `program_type` | — | points \| miles \| cashback \| other |
| `membership_id` | **New** | String — loyalty/membership number (nullable) |
| `unit_name` | — | "points", "miles", "%" |
| `cents_per_unit` | — | Valuation e.g., 1.5 |
| `current_balance` | **New** | Float — latest balance, set on each scrape |
| `active` | — | existing |
| `display_icon_url` | — | existing |
| `created_at`, `updated_at` | — | existing |

### `RewardsBalance` (unchanged)

Stores historical balance snapshots. `current_balance` on `RewardsProgram` is updated on each scrape; history is preserved here.

### `FinancialAccountType` (unchanged)

Existing `FinancialAccountType` / `balance_type` system is unaffected. Rewards are not `FinancialAccount` rows — they're separate.

---

## Backend Changes

### `accounts_db.py`

- Add `current_balance` column to `RewardsProgram` queries in `get_rewards_summary()`
- Update `get_rewards_summary()` to include monetary_value in asset total

### `api.py`

- `RewardsProgramBase` schema: add `scraper_login_id` (required), `financial_account_id` (optional), `membership_id` (optional), `current_balance` (optional)
- Update `create_rewards_program` and `update_rewards_program` endpoints to accept these fields
- No change to existing CRUD endpoints — add new fields to existing schemas

### Scraper Integration

- When a scraper run captures rewards balance data, update `RewardsProgram.current_balance` along with a `RewardsBalance` row

---

## Frontend Changes

### Navigation Tree (App.vue)

```js
{ id: 'assets', label: 'Assets', count: assetRows.value.length, children: [
  { id: 'rewards', label: 'Rewards', count: rewards.value.length },
]},
```

Rewards moves under Assets (was previously a top-level section).

### New `RewardsSection.vue` Component

Mirrors `BillsSection.vue` pattern:

```
Assets
├── [AccountsTable — checking, savings, brokerage, etc.]
└── Rewards (sub-section, collapsed by default in sidebar)
    └── [RewardsTable — program, balance, value, linked account/membership, actions]
```

**RewardsTable columns:**
- Account / Login (who manages this program)
- Program name
- Membership ID (if set)
- Balance (formatted: "52,000 pts" / "38,000 miles")
- Est. Value (≈ $780)
- Actions (edit, sync)

### `useRewards.js` (modified)

- `fetchRewardsSummary()` already returns the right shape — no major changes needed
- May need to expose `scraper_login_id` and `membership_id` in the form

### Summary Cards

- `asset_total` in summary already comes from the API
- Ensure `get_rewards_summary()` returns a `total_monetary_value` that gets added to the asset sum

### AssetsSection.vue (minimal change)

No structural change — just the rewards sub-section is added alongside it in the template.

### Existing `RewardsPanel.vue` and `RewardsDialog.vue`

Stay as-is. They handle add/edit of programs. They remain accessible via the sidebar (Assets → Rewards → Add button).

---

## Migration

New columns added to `rewards_programs` table:

```sql
ALTER TABLE rewards_programs
  ADD COLUMN scraper_login_id INTEGER
    REFERENCES scraper_logins(id) ON DELETE SET NULL;

ALTER TABLE rewards_programs
  ADD COLUMN membership_id TEXT;

ALTER TABLE rewards_programs
  ADD COLUMN current_balance REAL;
```

Existing rows: `scraper_login_id` backfilled from existing `financial_account.login_id` where available. `financial_account_id` converted to nullable (allow NULL for rows where no account link exists).

---

## Summary of Changes

| File | Change |
|------|--------|
| `shiso/scraper/models/accounts.py` | Add `scraper_login_id` (required), `membership_id`, `current_balance` to `RewardsProgram` |
| `shiso/scraper/services/accounts_db.py` | Update queries, add `current_balance` tracking on scrape |
| `shiso/scraper/api.py` | Update `RewardsProgramBase` schema, endpoints |
| `shiso/dashboard/frontend/src/components/RewardsSection.vue` | **New** — sub-section table component |
| `shiso/dashboard/frontend/src/App.vue` | Move `RewardsPanel` under Assets in nav tree |
| `shiso/dashboard/frontend/src/composables/useRewards.js` | Add `scraper_login_id`, `membership_id` to form |
| `alembic/versions/*.py` | Migration for new columns |
