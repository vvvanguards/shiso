# Import Panel Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Richer import UX — parallel domain enrichment on upload, AI prompt filter bar, quick category chips, collapsible domain groups.

**Architecture:** Backend adds `enrich_domain_metadata()` for web lookups per unique domain on CSV upload. Results upsert `provider_mappings` with `login_url`, `favicon_url`, `is_financial`. Frontend replaces Toolbar with filter bar + domain-grouped DataTable.

**Tech Stack:** Python (FastAPI, SQLAlchemy, Alembic), Vue 3, PrimeVue, Tailwind CSS

---

## File Map

| File | Change |
|---|---|
| `shiso/scraper/alembic/versions/XXX_enrich_provider_mappings.py` | Migration: add `login_url`, `favicon_url`, `is_financial` to `provider_mappings` |
| `shiso/scraper/models/accounts.py` | Add `login_url`, `favicon_url`, `is_financial` to `ProviderMapping` model |
| `shiso/scraper/services/provider_matcher.py` | Add `enrich_domain_metadata(domain)` — HTTP fetch + Open Graph parsing |
| `shiso/scraper/api.py` | Modify `import_start` to call enrichment in parallel after parsing |
| `shiso/dashboard/frontend/src/composables/useImport.js` | Add filter state (`query`, `activeCategories`), `filteredCandidates` computed, `enrichmentProgress` ref |
| `shiso/dashboard/frontend/src/components/ImportPanel.vue` | Replace Toolbar with filter bar + collapsible domain groups |

---

## Task 1: DB Migration — Add provider_mappings enrichment fields

**Files:**
- Create: `shiso/scraper/alembic/versions/XXX_add_enrichment_fields_to_provider_mappings.py`

- [ ] **Step 1: Create migration**

```python
"""add enrichment fields to provider_mappings

Revision ID: <generated>
Revises: <current head>
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '<generated>'
down_revision: Union[str, None] = '<current>'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

def upgrade() -> None:
    op.add_column('provider_mappings', sa.Column('login_url', sa.Text, nullable=True))
    op.add_column('provider_mappings', sa.Column('favicon_url', sa.Text, nullable=True))
    op.add_column('provider_mappings', sa.Column('is_financial', sa.Boolean, nullable=True))

def downgrade() -> None:
    op.drop_column('provider_mappings', 'is_financial')
    op.drop_column('provider_mappings', 'favicon_url')
    op.drop_column('provider_mappings', 'login_url')
```

Find current head with: `python -c "from shiso.scraper.alembic.env import current_head; print(current_head)"` or check the versions directory.

- [ ] **Step 2: Run migration**

Run: `python -m shiso.scraper.alembic.env upgrade`
Expected: adds 3 new nullable columns to `provider_mappings` table

- [ ] **Step 3: Commit**

```bash
git add shiso/scraper/alembic/versions/XXX_add_enrichment_fields_to_provider_mappings.py
git commit -m "feat: add login_url, favicon_url, is_financial to provider_mappings"
```

---

## Task 2: Update ProviderMapping model

**Files:**
- Modify: `shiso/scraper/models/accounts.py:197-211` (ProviderMapping class)

- [ ] **Step 1: Add fields to ProviderMapping model**

In `ProviderMapping.__tablename__ = "provider_mappings"` section, add after `confidence` field:

```python
login_url: Mapped[Optional[str]] = mapped_column(Text)
favicon_url: Mapped[Optional[str]] = mapped_column(Text)
is_financial: Mapped[Optional[bool]] = mapped_column(Boolean)
```

- [ ] **Step 2: Commit**

```bash
git add shiso/scraper/models/accounts.py
git commit -m "feat: add enrichment fields to ProviderMapping model"
```

---

## Task 3: Add `enrich_domain_metadata()` to provider_matcher

**Files:**
- Modify: `shiso/scraper/services/provider_matcher.py`

- [ ] **Step 1: Add `enrich_domain_metadata()` function**

Add at the end of `provider_matcher.py`:

```python
async def enrich_domain_metadata(domain: str) -> dict[str, Any] | None:
    """Fetch a domain's login page and extract Open Graph metadata.

    Returns dict with keys: domain, login_url, favicon_url, is_financial, label, category.
    Returns None on failure (non-critical — log and continue).
    """
    import asyncio
    import re
    from urllib.parse import urlparse

    # Try to find a login URL for the domain
    login_url = f"https://{domain}"
    favicon_url = f"https://{domain}/favicon.ico"
    is_financial = None
    label = domain.split('.')[0].capitalize()
    category = "Other"

    try:
        import httpx
        async with asyncio.timeout(8):
            try:
                resp = await httpx.AsyncClient(follow_redirects=True).get(login_url, timeout=8.0)
                html = resp.text

                # Extract og:title for label
                og_title_match = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
                if not og_title_match:
                    og_title_match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']', html, re.I)
                if og_title_match:
                    label = og_title_match.group(1).split('|')[0].split('-')[0].strip()

                # Extract og:description for category hints
                og_desc = ""
                desc_match = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
                if desc_match:
                    og_desc = desc_match.group(1).lower()

                # Try to find a login URL from common patterns
                login_patterns = [
                    r'href=["\']([^"\']*login[^"\']*)["\']',
                    r'href=["\']([^"\']*signin[^"\']*)["\']',
                    r'action=["\']([^"\']*login[^"\']*)["\']',
                ]
                for pattern in login_patterns:
                    m = re.search(pattern, html, re.I)
                    if m:
                        href = m.group(1)
                        if href.startswith('/'):
                            parsed = urlparse(login_url)
                            login_url = f"{parsed.scheme}://{parsed.netloc}{href}"
                        elif href.startswith('http'):
                            login_url = href
                        break

                # Heuristic: detect financial institution
                financial_keywords = ['bank', 'credit', 'loan', 'investment', 'insurance', 'mortgage', 'wealth', 'capital', 'fidelity', 'vanguard', 'schwab', 'chase', 'citi', 'amex', 'discover', 'wells Fargo', 'bank of america']
                is_financial = any(kw in og_desc or kw in label.lower() for kw in financial_keywords)

                # Try to infer category from page content
                if any(k in og_desc for k in ['bank', 'credit union', 'lending']):
                    category = "Bank"
                elif any(k in og_desc for k in ['credit card', 'rewards', 'miles']):
                    category = "Credit Card"
                elif any(k in og_desc for k in ['insurance', 'coverage', 'quote']):
                    category = "Insurance"
                elif any(k in og_desc for k in ['electric', 'gas', 'water', 'utility', 'energy']):
                    category = "Utility"

                return {
                    "domain": domain,
                    "login_url": login_url,
                    "favicon_url": favicon_url,
                    "is_financial": is_financial,
                    "label": label,
                    "category": category,
                }
            except Exception:
                # Fallback: preserve login_url/favicon_url, use domain as label
                return {
                    "domain": domain,
                    "login_url": login_url,
                    "favicon_url": favicon_url,
                    "is_financial": None,
                    "label": domain.split('.')[0].capitalize(),
                    "category": "Other",
                }
    except asyncio.TimeoutError:
        logger.warning("Enrichment timeout for domain: %s", domain)
        return None
    except Exception as exc:
        logger.warning("Enrichment failed for domain %s: %s", domain, exc)
        return None
```

- [ ] **Step 2: Add `httpx` to pyproject.toml if not present**

Check: `grep -i httpx pyproject.toml`
If not found, add: `"httpx>=0.27.0",` to dependencies.

- [ ] **Step 3: Commit**

```bash
git add shiso/scraper/services/provider_matcher.py pyproject.toml
git commit -m "feat: add enrich_domain_metadata for parallel domain enrichment"
```

---

## Task 4: Modify `POST /api/logins/import/start` to run enrichment

**Files:**
- Modify: `shiso/scraper/services/accounts_db.py` (`upsert_provider_mapping` method)
- Modify: `shiso/scraper/api.py` (around the `import_start` endpoint)
- Modify: `shiso/dashboard/main.py` (the `import_start` function)

Note: The `import_start` endpoint lives in `main.py` as `import_start`. Check both files.

- [ ] **Step 1: Update `upsert_provider_mapping` to accept enrichment fields**

In `accounts_db.py`, update `upsert_provider_mapping` to accept and store the new enrichment fields. Add `login_url`, `favicon_url`, and `is_financial` as optional parameters:

```python
def upsert_provider_mapping(
    self,
    domain_pattern: str,
    provider_key: str,
    label: str,
    account_type: str,
    source: str = "learned",
    confidence: float | None = None,
    login_url: str | None = None,
    favicon_url: str | None = None,
    is_financial: bool | None = None,
) -> ProviderMapping:
    """Insert or update a provider mapping."""
    with self.session() as session:
        existing = session.query(ProviderMapping).filter(
            ProviderMapping.domain_pattern == domain_pattern
        ).first()
        if existing:
            existing.provider_key = provider_key
            existing.label = label
            existing.account_type = account_type
            existing.source = source
            existing.confidence = confidence
            if login_url is not None:
                existing.login_url = login_url
            if favicon_url is not None:
                existing.favicon_url = favicon_url
            if is_financial is not None:
                existing.is_financial = is_financial
        else:
            mapping = ProviderMapping(
                domain_pattern=domain_pattern,
                provider_key=provider_key,
                label=label,
                account_type=account_type,
                source=source,
                confidence=confidence,
                login_url=login_url,
                favicon_url=favicon_url,
                is_financial=is_financial,
            )
            session.add(mapping)
            existing = mapping
        session.commit()
        session.refresh(existing)
        return existing
```

- [ ] **Step 2: Modify `import_start` to run parallel enrichment**

In `import_start` in `main.py`, after calling `match_providers_sync(raw_rows)` and `create_import_session`, add:

```python
# Fire enrichment for all unique domains in parallel
unique_domains = list(set(r.get("domain", "") for r in raw_rows if r.get("domain")))
enrichment_tasks = []
for domain in unique_domains:
    # Only enrich if not already in provider_mappings with label
    existing = db.get_provider_mappings(source="enriched")
    if not any(m["domain_pattern"] == domain for m in existing):
        from shiso.scraper.services.provider_matcher import enrich_domain_metadata
        import asyncio
        enrichment_tasks.append(asyncio.create_task(enrich_domain_metadata(domain)))

# Wait for all enrichment (with timeout), tracking progress
enriched_count = 0
enrichment_total = len(enrichment_tasks)
if enrichment_tasks:
    import asyncio
    done, pending = await asyncio.wait(enrichment_tasks, timeout=15.0)
    for task in pending:
        task.cancel()
    for task in done:
        result = task.result()
        if result:
            enriched_count += 1
            # Upsert into provider_mappings with enrichment fields
            db.upsert_provider_mapping(
                domain_pattern=result.get("domain", ""),
                provider_key=result.get("provider_key", ""),
                label=result.get("label", ""),
                account_type=result.get("category", "Other"),
                source="enriched",
                login_url=result.get("login_url"),
                favicon_url=result.get("favicon_url"),
                is_financial=result.get("is_financial"),
            )

# Return enrichment summary in response for frontend to display
enrichment_result = {"current": enriched_count, "total": enrichment_total}
```

Also update the response returned to the client to include `enrichment_result`:
```python
return {
    "session_id": session_id,
    "candidates": candidates,
    "enrichment_result": enrichment_result,  # e.g. {"current": 12, "total": 12}
    ...
}
```

- [ ] **Step 3: Wire up `enrichmentProgress` in `useImport.js` from response**

In `handleFileUpload` (in `useImport.js`), after `importSession.value = result`, read the enrichment result:
```javascript
if (result.enrichment_result) {
  enrichmentProgress.value = result.enrichment_result
} else {
  enrichmentProgress.value = null
}
```

- [ ] **Step 4: Commit**

```bash
git add shiso/scraper/services/accounts_db.py shiso/scraper/api.py shiso/dashboard/main.py shiso/dashboard/frontend/src/composables/useImport.js
git commit -m "feat: run parallel domain enrichment on CSV import"
```

---

## Task 5: Update `useImport.js` composable

**Files:**
- Modify: `shiso/dashboard/frontend/src/composables/useImport.js`

- [ ] **Step 1: Add filter state**

Add to the composable:

```javascript
const searchQuery = ref('')
const activeCategories = ref([])  // empty = all shown
const enrichmentProgress = ref(null)  // null | { current: number, total: number }
```

- [ ] **Step 2: Add `filteredCandidates` computed**

```javascript
const filteredCandidates = computed(() => {
  let results = candidates.value

  // "Selected Only" chip
  if (activeCategories.value.includes('selected_only')) {
    const selectedIds = new Set(selectedRows.value.map(r => r.id))
    results = results.filter(c => selectedIds.has(c.id))
  }

  // Category filter (skip 'selected_only' which is not an account type)
  const typeChips = activeCategories.value.filter(k => k !== 'selected_only')
  if (typeChips.length > 0) {
    results = results.filter(c => typeChips.includes(c.account_type))
  }

  // Search filter
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase()
    results = results.filter(c =>
      (c.domain || '').toLowerCase().includes(q) ||
      (c.name || '').toLowerCase().includes(q) ||
      (c.username || '').toLowerCase().includes(q) ||
      (c.label || '').toLowerCase().includes(q) ||
      (c.provider_key || '').toLowerCase().includes(q)
    )
  }

  return results
})
```

- [ ] **Step 3: Add `toggleCategory` helper**

```javascript
function toggleCategory(cat) {
  const idx = activeCategories.value.indexOf(cat)
  if (idx >= 0) {
    activeCategories.value.splice(idx, 1)
  } else {
    activeCategories.value.push(cat)
  }
}

function clearFilters() {
  searchQuery.value = ''
  activeCategories.value = []
}
```

- [ ] **Step 4: Return new state**

Update the return statement:
```javascript
return {
  importSession,
  importing,
  handleFileUpload,
  runImportFromSelection,
  cancelImport,
  // new:
  searchQuery,
  activeCategories,
  filteredCandidates,
  enrichmentProgress,
  toggleCategory,
  clearFilters,
}
```

- [ ] **Step 5: Commit**

```bash
git add shiso/dashboard/frontend/src/composables/useImport.js
git commit -m "feat: add filter state to useImport composable"
```

---

## Task 6: Redesign ImportPanel.vue

**Files:**
- Modify: `shiso/dashboard/frontend/src/components/ImportPanel.vue`

- [ ] **Step 1: Replace Toolbar with filter bar**

Remove the `<Toolbar>` block. Replace with:

```html
<!-- Enrichment progress (shown during upload) -->
<div v-if="enrichmentProgress" class="mb-4 flex items-center gap-2 text-sm text-shiso-400">
  <i class="pi pi-spin pi-spinner" />
  <span>Enriching {{ enrichmentProgress.current }} / {{ enrichmentProgress.total }} domains...</span>
</div>

<!-- Filter bar -->
<div v-if="importSession" class="mb-4 flex flex-col gap-3">
  <!-- AI prompt + search -->
  <div class="flex items-center gap-3">
    <span class="text-xs font-semibold text-shiso-500 uppercase tracking-wider">Search:</span>
    <InputText
      v-model="searchQuery"
      placeholder="Filter: credit cards, banks, chase..."
      class="flex-1"
      size="small"
    />
    <div class="flex gap-2">
      <Button @click="clearFilters" label="Clear" severity="secondary" size="small" outlined :disabled="!searchQuery && !activeCategories.length" />
      <Button @click="selectAll" label="All" severity="secondary" size="small" outlined />
      <Button @click="deselectAll" label="None" severity="secondary" size="small" outlined />
      <Button @click="onCancel" label="Cancel" severity="secondary" size="small" outlined />
      <Button
        @click="handleImport"
        :loading="importing"
        :label="importButtonLabel"
        :disabled="!selectedCount"
        severity="success"
        size="small"
      />
    </div>
  </div>

  <!-- Category chips -->
  <div class="flex flex-wrap gap-2 items-center">
    <span class="text-xs font-semibold text-shiso-500 uppercase tracking-wider mr-1">Filter:</span>
    <template v-for="cat in CATEGORIES" :key="cat.key">
      <Button
        :label="cat.label"
        :icon="cat.icon"
        size="small"
        :severity="activeCategories.includes(cat.key) ? 'primary' : 'secondary'"
        :outlined="!activeCategories.includes(cat.key)"
        @click="toggleCategory(cat.key)"
        class="text-xs"
      />
    </template>
  </div>
</div>
```

Add `CATEGORIES` constant to `<script setup>`:
```javascript
const CATEGORIES = [
  { key: 'Bank', label: '🏦 Banks' },
  { key: 'Credit Card', label: '💳 Credit Cards' },
  { key: 'Loan', label: '🏠 Loans / Mortgage' },
  { key: 'Utility', label: '💡 Utilities' },
  { key: 'Insurance', label: '🔒 Insurance' },
  { key: 'selected_only', label: '✓ Selected Only' },
]
```

- [ ] **Step 2: Group candidates by domain**

Add computed `groupedCandidates`:
```javascript
const groupedCandidates = computed(() => {
  const groups = {}
  for (const c of filteredCandidates.value) {
    const domain = c.domain || 'unknown'
    if (!groups[domain]) {
      groups[domain] = {
        domain,
        label: c.label || domain,
        rows: [],
      }
    }
    groups[domain].rows.push(c)
  }
  return Object.values(groups).sort((a, b) => a.domain.localeCompare(b.domain))
})
```

- [ ] **Step 3: Replace DataTable with collapsible domain groups**

Remove the flat `<DataTable>`. Replace with:

```html
<div v-for="group in groupedCandidates" :key="group.domain" class="mb-3">
  <!-- Group header -->
  <div
    class="flex items-center justify-between px-3 py-2 bg-shiso-800 rounded-t-lg border border-shiso-700 cursor-pointer"
    @click="toggleGroup(group.domain)"
  >
    <div class="flex items-center gap-2">
      <i :class="expandedGroups.includes(group.domain) ? 'pi pi-chevron-down' : 'pi pi-chevron-right'" style="font-size: 0.75rem" />
      <span class="font-medium text-sm">{{ group.label }}</span>
      <span class="text-xs text-shiso-500">({{ group.domain }})</span>
    </div>
    <div class="flex gap-2 items-center">
      <span class="text-xs text-shiso-400">{{ group.rows.length }} {{ group.rows.length === 1 ? 'login' : 'logins' }}</span>
      <Checkbox
        :modelValue="group.rows.every(r => selectedRows.find(s => s.id === r.id))"
        :indeterminate="group.rows.some(r => selectedRows.find(s => s.id === r.id)) && !group.rows.every(r => selectedRows.find(s => s.id === r.id))"
        @update:modelValue="(val) => toggleGroupSelection(group, val)"
        binary
      />
    </div>
  </div>

  <!-- Group rows (only shown when expanded) -->
  <DataTable
    v-if="expandedGroups.includes(group.domain)"
    :value="group.rows"
    v-model:selection="selectedModelForGroup(group.rows)"
    dataKey="id"
    size="small"
    :rowClass="(data) => data.is_duplicate && data.existing_login_is_deleted ? 'bg-red-900/20 opacity-50' : data.is_duplicate ? 'opacity-50' : ''"
  >
    <Column style="width: 2rem">
      <template #body="{ data }">
        <Checkbox
          v-model="selectedRows"
          :value="data"
          @change="selectedRows = [...selectedRows]"
        />
      </template>
    </Column>
    <Column header="Username">
      <template #body="{ data }">
        <div class="flex flex-col">
          <span>{{ data.username }}</span>
          <a :href="data.url" target="_blank" class="text-xs text-shiso-500 hover:text-shiso-300 truncate max-w-[200px]">{{ data.url }}</a>
        </div>
      </template>
    </Column>
    <Column header="Provider">
      <template #body="{ data }">
        <div class="flex flex-col gap-1">
          <span class="text-sm" :class="!data.provider_key ? 'text-orange-400' : ''">{{ data.label || data.domain }}</span>
          <span v-if="!data.provider_key" class="text-xs text-orange-400">No match — will import as-is</span>
        </div>
      </template>
    </Column>
    <Column header="Status" style="width: 7rem">
      <template #body="{ data }">
        <Tag v-if="data.is_duplicate && data.existing_login_is_deleted" value="deleted" severity="danger" />
        <Tag v-else-if="data.is_duplicate" value="exists" severity="warn" />
        <Tag v-else value="new" severity="success" />
      </template>
    </Column>
  </DataTable>
</div>

<!-- Empty state -->
<div v-if="groupedCandidates.length === 0 && importSession" class="text-center py-8 text-shiso-400 text-sm">
  No logins match your filters.
</div>
```

Add to `<script setup>`:
```javascript
const expandedGroups = ref([])

watch(groupedCandidates, (groups) => {
  // Auto-expand groups when they appear
  expandedGroups.value = groups.map(g => g.domain)
}, { immediate: true })

function toggleGroup(domain) {
  const idx = expandedGroups.value.indexOf(domain)
  if (idx >= 0) expandedGroups.value.splice(idx, 1)
  else expandedGroups.value.push(domain)
}

function toggleGroupSelection(group, selectAll) {
  if (selectAll) {
    const ids = new Set(selectedRows.value.map(r => r.id))
    for (const row of group.rows) ids.add(row.id)
    selectedRows.value = [...ids].map(id => selectedRows.value.find(r => r.id === id) || group.rows.find(r => r.id === id)).filter(Boolean)
  } else {
    selectedRows.value = selectedRows.value.filter(r => !group.rows.find(gr => gr.id === r.id))
  }
}

function selectedModelForGroup(groupRows) {
  return computed({
    get: () => selectedRows.value.filter(r => groupRows.find(gr => gr.id === r.id)),
    set: (val) => {
      const other = selectedRows.value.filter(r => !groupRows.find(gr => gr.id === r.id))
      selectedRows.value = [...other, ...val]
    }
  })
}
```

Add to imports:
```javascript
import Checkbox from 'primevue/checkbox'
import InputText from 'primevue/inputtext'
```

- [ ] **Step 4: Update computed stats (top bar)**

Replace the tag counts with filtered counts:
```html
<div class="flex items-center gap-3 text-sm mb-2">
  <Tag :value="`${candidates.length} total`" severity="secondary" />
  <Tag :value="`${filteredCandidates.length} shown`" severity="info" />
  <Tag v-if="duplicateCount" :value="`${duplicateCount} duplicates`" severity="warn" />
  <Tag :value="`${selectedCount} selected`" severity="success" />
</div>
```

- [ ] **Step 5: Commit**

```bash
git add shiso/dashboard/frontend/src/components/ImportPanel.vue
git commit -m "feat: redesign ImportPanel with filter bar and domain groups"
```

---

## Task 7: Manual testing checklist

After all tasks complete:

- [ ] Upload a Chrome password CSV with 5+ logins across 2+ domains
- [ ] Verify enrichment spinner appears during upload
- [ ] Verify domain groups appear collapsed/expanded
- [ ] Verify category chips filter the table correctly
- [ ] Verify search filters by domain, name, username
- [ ] Verify select-all, deselect-all, per-group selection
- [ ] Verify duplicates are dimmed with correct badge
- [ ] Verify import confirmation works end-to-end
