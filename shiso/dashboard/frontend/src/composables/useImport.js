import { ref } from 'vue'
import { useToast } from 'primevue/usetoast'
import { importStart, confirmImport, deleteImport } from '../api.js'

const importSession = ref(null)
const importing = ref(false)

export function useImport() {
  const toast = useToast()

  async function handleFileUpload(event) {
    const file = event.files[0]
    if (!file) return
    importing.value = true
    try {
      const result = await importStart(file)
      importSession.value = result
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
  }

  return {
    importSession,
    importing,
    handleFileUpload,
    runImportFromSelection,
    cancelImport,
  }
}
