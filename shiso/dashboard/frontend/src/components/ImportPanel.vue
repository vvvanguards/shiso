<template>
  <Section header="Import Passwords" :collapsed="true" persistKey="import" class="mb-12">
    <div v-if="!importSession">
      <div class="flex items-center gap-4">
        <FileUpload
          mode="basic"
          accept=".csv"
          :auto="true"
          chooseLabel="Choose CSV File"
          customUpload
          @uploader="handleUpload"
          :loading="importing"
        />
        <span class="text-sm text-surface-400">Export from chrome://password-manager/settings</span>
      </div>
    </div>

    <div v-else>
      <!-- Enrichment progress (shown during upload) -->
      <div v-if="enrichmentProgress" class="mb-4 flex items-center gap-2 text-sm text-shiso-400">
        <i class="pi pi-spin pi-spinner" />
        <span>Enriching {{ enrichmentProgress.current }} / {{ enrichmentProgress.total }} domains...</span>
      </div>

      <!-- Filter bar -->
      <div class="mb-4 flex flex-col gap-3">
        <!-- AI prompt + search -->
        <div class="flex items-center gap-3">
          <span class="text-xs font-semibold text-shiso-500 uppercase tracking-wider">Search:</span>
          <InputText
            :modelValue="searchQuery"
            @update:modelValue="onSearchInput"
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

        <!-- Category chips + mode badges -->
        <div class="flex flex-wrap gap-2 items-center justify-between">
          <div class="flex flex-wrap gap-2 items-center">
            <span class="text-xs font-semibold text-shiso-500 uppercase tracking-wider mr-1">Filter:</span>
            <template v-for="cat in CATEGORIES" :key="cat.key">
              <Button
                :label="cat.label"
                size="small"
                :severity="activeCategories.includes(cat.key) ? 'primary' : 'secondary'"
                :outlined="!activeCategories.includes(cat.key)"
                @click="toggleCategory(cat.key)"
                class="text-xs"
              />
            </template>
          </div>
          <!-- Mode badges (existing behavior retained) -->
          <div class="flex gap-1 items-center">
            <span class="text-xs text-shiso-500 mr-1">Mode:</span>
            <Button v-for="mode in ['Rule', 'LLM', 'Off']" :key="mode"
              :label="mode"
              size="small"
              :severity="filterMode === mode ? 'primary' : 'secondary'"
              :outlined="filterMode !== mode"
              @click="filterMode = mode"
              class="text-xs"
            />
          </div>
        </div>
      </div>

      <!-- Stats bar -->
      <div class="flex items-center gap-3 text-sm mb-2">
        <Tag :value="`${candidates.length} total`" severity="secondary" />
        <Tag :value="`${filteredCandidates.length} shown`" severity="info" />
        <Tag v-if="duplicateCount" :value="`${duplicateCount} duplicates`" severity="warn" />
        <Tag :value="`${selectedCount} selected`" severity="success" />
      </div>

      <!-- Collapsible domain groups -->
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
      <div v-if="groupedCandidates.length === 0" class="text-center py-8 text-shiso-400 text-sm">
        No logins match your filters.
      </div>
    </div>
  </Section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import FileUpload from 'primevue/fileupload'
import InputText from 'primevue/inputtext'
import Tag from 'primevue/tag'
import Section from './Section.vue'

const props = defineProps({
  importSession: { type: Object, default: null },
  importing: { type: Boolean, default: false },
})

const emit = defineEmits(['upload', 'import', 'cancel'])

const CATEGORIES = [
  { key: 'Bank', label: '🏦 Banks' },
  { key: 'Credit Card', label: '💳 Credit Cards' },
  { key: 'Loan', label: '🏠 Loans / Mortgage' },
  { key: 'Utility', label: '💡 Utilities' },
  { key: 'Insurance', label: '🔒 Insurance' },
  { key: 'selected_only', label: '✓ Selected Only' },
]

const filterMode = ref('Rule')  // 'Rule' | 'LLM' | 'Off'
const expandedGroups = ref([])

const selectedModel = computed({
  get: () => selectedRows.value,
  set: (val) => { selectedRows.value = val },
})

const candidates = computed(() => props.importSession?.candidates || [])

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

watch(groupedCandidates, (groups) => {
  // Auto-expand groups when they appear
  expandedGroups.value = groups.map(g => g.domain)
}, { immediate: true })

const duplicateCount = computed(() => {
  return candidates.value.filter(c => c.is_duplicate).length
})

const selectedCount = computed(() => selectedRows.value.length)

const importButtonLabel = computed(() => {
  if (!selectedCount.value) return 'Import 0 Selected'
  const newCount = selectedRows.value.filter(r => !r.is_duplicate).length
  const dupeCount = selectedRows.value.filter(r => r.is_duplicate && !r.existing_login_is_deleted).length
  const deletedDupeCount = selectedRows.value.filter(r => r.is_duplicate && r.existing_login_is_deleted).length
  const parts = []
  if (newCount) parts.push(`${newCount} new`)
  if (dupeCount) parts.push(`${dupeCount} update`)
  if (deletedDupeCount) parts.push(`${deletedDupeCount} reactivate`)
  return `Import (${parts.join(', ')})`
})

// --- Filter state (wired from useImport) ---
import { useImport } from '../composables/useImport.js'
const { searchQuery, activeCategories, enrichmentProgress, toggleCategory, clearFilters, setSearchQuery, selectedRows } = useImport()

function onSearchInput(val) {
  setSearchQuery(val)
}

watch(candidates, (newCandidates) => {
  selectedRows.value = newCandidates.filter(c => !c.is_duplicate || !c.existing_login_is_deleted)
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

function selectAll() {
  selectedRows.value = [...filteredCandidates.value]
}

function deselectAll() {
  selectedRows.value = []
}

function handleUpload(event) {
  emit('upload', event)
}

function handleImport() {
  const selectedIds = selectedRows.value.map(r => r.id)
  emit('import', selectedIds)
}

function onCancel() {
  selectedRows.value = []
  clearFilters()
  emit('cancel')
}
</script>
