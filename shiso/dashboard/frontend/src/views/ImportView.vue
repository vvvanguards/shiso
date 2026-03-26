<template>
  <div class="mx-auto max-w-7xl space-y-6">
    <ImportPanel
      :importSession="importSession"
      :importing="importing"
      @upload="handleFileUpload"
      @import="(ids) => runImportFromSelection(ids, loadLogins)"
      @cancel="cancelImport"
    />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'

import ImportPanel from '../components/ImportPanel.vue'
import { useImport } from '../composables/useImport.js'
import { useLogins } from '../composables/useLogins.js'

const {
  importSession, importing, handleFileUpload, runImportFromSelection, cancelImport,
} = useImport()

const { loadLogins } = useLogins()

onMounted(loadLogins)
</script>
