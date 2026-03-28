import { computed, ref, watch } from 'vue'
import { useToast } from 'primevue/usetoast'
import { importStart, confirmImport, deleteImport } from '../api.js'

const importSession = ref(null)
const importing = ref(false)
const searchQuery = ref('')
const activeCategories = ref([])  // empty = all shown
const enrichmentProgress = ref(null)  // null | { current: number, total: number }
const selectedRows = ref([])

let searchDebounceTimer = null

function debounceSearch(fn, delay) {
  return function(val) {
    clearTimeout(searchDebounceTimer)
    searchDebounceTimer = setTimeout(() => fn(val), delay)
  }
}

export function useImport() {
  const toast = useToast()

  const candidates = computed(() => importSession.value?.candidates || [])

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

  function setSearchQuery(val) {
    searchDebounceTimer = setTimeout(() => {
      searchQuery.value = val
    }, 200)
  }

  async function handleFileUpload(event) {
    const file = event.files[0]
    if (!file) return
    importing.value = true
    try {
      const result = await importStart(file)
      importSession.value = result
      selectedRows.value = result.candidates?.filter(c => !c.is_duplicate || !c.existing_login_is_deleted) || []
      if (result.enrichment_result) {
        enrichmentProgress.value = result.enrichment_result
      } else {
        enrichmentProgress.value = null
      }
    } catch (err) {
      toast.add({ severity: 'error', summary: 'Import Error', detail: err.message, life: 4000 })
      importSession.value = null
    } finally {
      importing.value = false
    }
  }

  async function runImportFromSelection(selectedIds, onSuccess) {
    if (!importSession.value?.session_id || !selectedIds?.length) return
    importing.value = true
    try {
      const result = await confirmImport(importSession.value.session_id, selectedIds)
      const parts = []
      if (result.imported) parts.push(`${result.imported} imported`)
      if (result.updated) parts.push(`${result.updated} updated`)
      toast.add({ severity: 'success', summary: 'Import Complete', detail: parts.join(', '), life: 5000 })
      importSession.value = null
      if (onSuccess) await onSuccess()
    } catch (err) {
      toast.add({ severity: 'error', summary: 'Import Failed', detail: err.message, life: 4000 })
    } finally {
      importing.value = false
    }
  }

  async function cancelImport() {
    if (!importSession.value?.session_id) return
    try {
      await deleteImport(importSession.value.session_id)
    } catch (_) {
      // ignore delete errors
    }
    importSession.value = null
    clearFilters()
    selectedRows.value = []
  }

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
    setSearchQuery,
    selectedRows,
  }
}
