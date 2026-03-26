# Import Panel Redesign — Spec

**Date**: 2026-03-26
**Status**: Draft

---

## What we're building

Richer UX for the CSV password import panel: AI prompt filtering, quick category toggles, smart search, and parallel domain enrichment on upload.

---

## Design Decisions

| Decision | Choice |
|---|---|
| Layout | Compact filter bar (single top row) |
| AI prompt bar | Yes — natural language filter input |
| Quick filter chips | Banks, Credit Cards, Loans, Utilities, Insurance, Selected Only |
| Search | Fuzzy, case-insensitive across domain, name, username, label, provider key |
| Domain grouping | Collapsible sections, grouped by domain |
| Enrichment | Parallel web lookups per unique domain on upload — enriches categories, login page, name, metadata |
| Duplicates | Mixed in table, dimmed + "exists"/"deleted" badge (same Status Tag as today) |

---

## Components

### Enrichment Phase (on upload)

After CSV parsing, before showing the table:

1. Extract all unique domains from the CSV rows
2. For each domain, fire a parallel enrichment lookup:
   - **Category** (bank, credit card, utility, insurance, loan, other)
   - **Login page URL** (direct login URL if discoverable)
   - **Cleaned name** (e.g. "Chase" from "chase.com")
   - **Metadata** (favicon URL, whether it's a known financial institution)
3. Results stored in `provider_mappings` table (upsert by domain_pattern), `source = "enriched"`
4. Show a progress indicator: "Enriching 12 domains..." with a spinner
5. Once all lookups complete, show the filter bar

Enrichment is idempotent — re-importing the same domain uses cached data.

### Top Filter Bar

Replaces the current `Toolbar` with a compact horizontal filter bar containing:

1. **AI Prompt Input** — `<input>` with placeholder hints. Triggers client-side filtering of loaded candidates on every keystroke (debounced 200ms). Tries to match as:
   - Provider/domain substring (e.g. "chase", "amex")
   - Account type keyword (e.g. "credit card", "bank", "utility")
   - Username or name substring
   - `selected` keyword → show only selected rows

2. **Quick Filter Chips** — Row of toggle chips:
   - 🏦 Banks
   - 💳 Credit Cards
   - 🏠 Loans / Mortgage
   - 💡 Utilities
   - 🔒 Insurance
   - ✓ Selected Only
   Each chip is multi-select. Active chips are highlighted blue. Clicking an active chip deselects it (toggle). When no category chips are active, all categories are shown.

3. **Mode Badges** — Rule / LLM / Off toggle (existing behavior, retained).

### Collapsible Domain Groups

Candidates grouped by domain. Each row is a login credential (username + URL), not a financial account. The enriched provider name appears in the group header:

```
▼ Chase (chase.com) (2)
  john.doe@gmail.com        https://chase.com     new
  JaneSmith@email.com        https://chase.com     exists [dimmed]
▼ Capital One (capitalone.com) (2)
  me@gmail.com               https://capitalone.com  new
  savings@gmail.com          https://capitalone.com  new
```

- Group header: enriched name + domain + count badge
- Clicking header expands/collapses the group
- All groups expanded by default
- Search/filter hides non-matching groups entirely

### DataTable (inside each group)

Columns:
- Site (enriched provider name + domain)
- Username
- Login URL
- Status (new / exists / deleted badge)

Duplicates: `opacity: 0.4`, background tint, "exists"/"deleted" Tag.

---

## Backend Changes

### `POST /api/logins/import/start` — add enrichment

**Existing endpoint** modified to:
1. Parse CSV → extract unique domains
2. For each domain not already in `provider_mappings`, fire a parallel enrichment lookup
3. Wait for all lookups to complete
4. Return enriched session + candidates

**Enrichment lookup** (per domain, run in parallel):
- Use the existing `match_providers` logic (which uses keyword + TOML config) as a fast first pass
- For unmatched domains, fire a web search/fetch for login page metadata
- Extract: category, login_url, cleaned label, favicon
- Upsert `provider_mappings` with `source = "enriched"`

**New `provider_mappings` fields** (added by migration):
- `login_url` (Text) — direct login URL
- `favicon_url` (Text) — favicon image URL
- `is_financial` (Boolean) — whether domain is a known financial institution

> The web lookup uses lightweight HTTP fetch + Open Graph parsing — no LLM needed. Fast and stateless.

### `POST /api/logins/import/{session_id}/filter` (stub for future)

Not implemented in v1. All filtering is client-side. This endpoint is a future hook if candidate lists grow large enough to warrant server-side filtering.

---

## UI Conventions

Follow existing patterns in the codebase:
- Use PrimeVue components (`DataTable`, `Column`, `Tag`, `Chips`, `InputText`)
- Tailwind classes matching the existing dark theme (`bg-shiso-*`, `text-shiso-*`)
- Existing `Section.vue` wrapper and `SectionHeader` pattern
- No custom CSS unless the library cannot achieve the needed look

---

## Files to Change

| File | Change |
|---|---|
| `src/components/ImportPanel.vue` | Replace Toolbar with new filter bar, domain grouping, enrichment progress |
| `src/composables/useImport.js` | Add filter state, computed filteredCandidates, enrichment progress tracking |
| `src/api.js` | Add `enrichDomain(domain)` for background enrichment (future) |
| `shiso/scraper/services/provider_matcher.py` | Add `enrich_domain_metadata(domain)` — web fetch + OG tag parsing |
| `shiso/scraper/models/accounts.py` | Add `login_url`, `favicon_url`, `is_financial` to `ProviderMapping` |
| `shiso/scraper/alembic/versions/` | Migration adding new ProviderMapping columns |
| `shiso/scraper/api.py` | Add `enrich_login` endpoint (optional, can be background) |

---

## Out of Scope

- LLM-powered prompt interpretation (client-side keyword matching only for now)
- Server-side filtering endpoint (stub only)
- Changing the CSV upload flow or confirmation UX
- Real-time collaborative enrichment
