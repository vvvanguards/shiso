# Import Panel Redesign — Spec

**Date**: 2026-03-26
**Status**: Draft

---

## What we're building

Richer UX for the CSV password import panel: AI prompt filtering, quick category toggles, smart search, and domain grouping.

---

## Design Decisions

| Decision | Choice |
|---|---|
| Layout | Compact filter bar (single top row) |
| AI prompt bar | Yes — natural language filter input |
| Quick filter chips | Banks, Credit Cards, Loans, Utilities, Insurance, Selected Only |
| Search | Fuzzy, case-insensitive across domain, name, username, label, provider key |
| Domain grouping | Collapsible sections, grouped by domain |
| Duplicates | Mixed in table, dimmed + "exists"/"deleted" badge (same Status Tag as today) |

---

## Components

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
   - 🏠 Loans
   - 💡 Utilities
   - 🔒 Insurance
   - ✓ Selected Only
   Each chip is multi-select. Active chips are highlighted blue. Clicking an active chip deselects it (toggle). When no category chips are active, all categories are shown.

3. **Mode Badges** — Rule / LLM / Off toggle (existing behavior, retained).

### Collapsible Domain Groups

Instead of a flat sorted table, candidates are grouped by domain:

```
▼ chase.com (3)
  Chase Sapphire Reserve     username@email    new
  Chase Total Checking       checking_user    new
  Chase Slate               card_user        exists [dimmed]
▼ capitalone.com (2)
  Capital One Venture X     me@email         new
  Capital One HYSA          savings_user     new
```

- Group header: domain name + count badge
- Clicking header expands/collapses the group
- All groups expanded by default
- Search/filter hides non-matching groups entirely

### DataTable (inside each group)

Columns unchanged from current:
- Site (name + domain)
- Username
- Provider (label; shown in orange text if `provider_key` is null — no match found in provider mappings)
- Status (new / exists / deleted badge)

Duplicates: `opacity: 0.4`, background tint, "exists"/"deleted" Tag.

---

## Backend Changes

### New endpoint: `POST /api/logins/import/{session_id}/filter`

**Request:**
```json
{ "query": "credit cards", "categories": ["banks"], "selected_only": false }
```

**Response:**
```json
{ "candidate_ids": [1, 3, 8], "total": 3 }
```

Returns IDs of candidates matching the query+category filter. Used when the candidate list is too large to filter efficiently client-side (future; initially all filtering is client-side).

> **Note**: AI prompt filtering is client-side only for now. If the user wants an LLM-powered natural language filter that actually interprets queries like "show me credit cards with high rewards", we can wire up the LLM classification endpoint later.

---

## Files to Change

| File | Change |
|---|---|
| `src/components/ImportPanel.vue` | Replace Toolbar with new filter bar, add domain grouping, search logic |
| `src/composables/useImport.js` | Add filter state (query, activeCategories), computed filteredCandidates |
| `src/api.js` | Add `filterImportCandidates` API call (future use) |

---

## Out of Scope

- LLM-powered prompt interpretation (client-side keyword matching only for now)
- Server-side filtering endpoint (stub only)
- Changing the CSV upload flow
- Import confirmation UX
