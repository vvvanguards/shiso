<template>
  <Section header="Import Passwords" :collapsed="true" persistKey="import" class="mb-12">
    <div v-if="!previewData" class="flex items-center gap-4">
      <FileUpload mode="basic" accept=".csv" :auto="true" chooseLabel="Choose CSV File" customUpload @uploader="handleUpload" />
      <span class="text-sm text-surface-400">Export from chrome://password-manager/settings</span>
    </div>

    <div v-else>
      <Toolbar class="mb-4">
        <template #start>
          <div class="flex items-center gap-3 text-sm">
            <Tag :value="`${previewData.matched.length} matched`" severity="success" />
            <Tag v-if="duplicateCount" :value="`${duplicateCount} existing`" severity="warn" />
            <Tag :value="`${previewData.unmatched.length} unmatched`" severity="secondary" />
            <Tag :value="`${selectedRows.length} selected`" severity="info" />
          </div>
        </template>
        <template #end>
          <div class="flex gap-2">
            <Button @click="showUnmatched = !showUnmatched" :label="showUnmatched ? 'Hide Unmatched' : 'Show Unmatched'" severity="secondary" size="small" outlined />
            <Button @click="emit('clear')" label="Clear" severity="secondary" size="small" outlined />
            <Button @click="handleImport" :loading="importing" :label="importButtonLabel" :disabled="!selectedRows.length" severity="success" size="small" />
          </div>
        </template>
      </Toolbar>

      <DataTable :value="previewData.matched" v-model:selection="selectionModel" dataKey="row_id" scrollable scrollHeight="400px" size="small">
        <Column selectionMode="multiple" headerStyle="width: 3rem" />
        <Column header="Provider">
          <template #body="{ data }">
            <div class="font-medium">{{ data.provider_label }}</div>
            <div class="text-xs text-surface-400">{{ data.provider_key }}</div>
          </template>
        </Column>
        <Column field="account_type" header="Type">
          <template #body="{ data }">
            <Tag :value="data.account_type" severity="secondary" />
          </template>
        </Column>
        <Column field="username" header="Username" />
        <Column header="Password">
          <template #body="{ data }">{{ data.has_password ? '••••••••' : '—' }}</template>
        </Column>
        <Column header="Status" style="width: 6rem">
          <template #body="{ data }">
            <Tag v-if="data.is_duplicate" value="exists" severity="warn" />
            <Tag v-else value="new" severity="success" />
          </template>
        </Column>
      </DataTable>

      <div v-if="showUnmatched" class="mt-4">
        <h3 class="text-sm uppercase tracking-widest text-surface-400 mb-2">Unmatched ({{ previewData.unmatched.length }})</h3>
        <DataTable :value="previewData.unmatched" scrollable scrollHeight="300px" size="small">
          <Column field="name" header="Site" />
          <Column field="username" header="Username">
            <template #body="{ data }">{{ data.username || '—' }}</template>
          </Column>
          <Column field="url" header="URL">
            <template #body="{ data }">
              <span class="text-xs text-surface-400 truncate block max-w-[300px]">{{ data.url }}</span>
            </template>
          </Column>
        </DataTable>
      </div>
    </div>
  </Section>
</template>

<script setup>
import { ref, computed } from 'vue'
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import FileUpload from 'primevue/fileupload'
import Tag from 'primevue/tag'
import Toolbar from 'primevue/toolbar'
import Section from './Section.vue'

const props = defineProps({
  previewData: { type: Object, default: null },
  importing: { type: Boolean, default: false },
})

const emit = defineEmits(['upload', 'import', 'clear'])

const showUnmatched = ref(false)
const selectedRows = ref([])

const selectionModel = computed({
  get: () => selectedRows.value,
  set: (val) => { selectedRows.value = val },
})

const duplicateCount = computed(() => {
  if (!props.previewData) return 0
  return props.previewData.matched.filter(r => r.is_duplicate).length
})

const importButtonLabel = computed(() => {
  const sel = selectedRows.value
  if (!sel.length) return 'Import 0 Selected'
  const newCount = sel.filter(r => !r.is_duplicate).length
  const dupeCount = sel.filter(r => r.is_duplicate).length
  const parts = []
  if (newCount) parts.push(`${newCount} new`)
  if (dupeCount) parts.push(`${dupeCount} update`)
  return `Import (${parts.join(', ')})`
})

function handleUpload(event) {
  emit('upload', event)
}

function handleImport() {
  emit('import', selectedRows.value)
}
</script>