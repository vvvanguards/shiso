import { shallowRef } from 'vue'
import { useToast } from 'primevue/usetoast'
import { importPreview, importLogins } from '../api.js'

const importFile = shallowRef(null)
const importPreviewData = shallowRef(null)
const importing = shallowRef(false)

export function useImport() {
  const toast = useToast()

  async function handleFileUpload(event) {
    const file = event.files[0]
    if (!file) return
    importFile.value = file
    try {
      importPreviewData.value = await importPreview(file)
    } catch (err) {
      toast.add({ severity: 'error', summary: 'Parse Error', detail: err.message, life: 4000 })
    }
  }

  function clearImport() {
    importPreviewData.value = null
    importFile.value = null
  }

  async function runImportFromSelection(selectedRows, onSuccess) {
    if (!importFile.value || !selectedRows.length) return
    importing.value = true
    try {
      const newIds = selectedRows.filter(r => !r.is_duplicate).map(r => r.row_id)
      const overwriteIds = selectedRows.filter(r => r.is_duplicate).map(r => r.row_id)
      const result = await importLogins(importFile.value, newIds, overwriteIds)
      const parts = []
      if (result.imported) parts.push(`${result.imported} imported`)
      if (result.updated) parts.push(`${result.updated} updated`)
      if (result.skipped) parts.push(`${result.skipped} skipped`)
      toast.add({ severity: 'success', summary: 'Import Complete', detail: parts.join(', '), life: 5000 })
      clearImport()
      if (onSuccess) await onSuccess()
    } catch (err) {
      toast.add({ severity: 'error', summary: 'Import Failed', detail: err.message, life: 4000 })
    } finally {
      importing.value = false
    }
  }

  return {
    importFile,
    importPreviewData,
    importing,
    handleFileUpload,
    clearImport,
    runImportFromSelection,
  }
}
