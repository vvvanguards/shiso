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
      <Toolbar class="mb-4">
        <template #start>
          <div class="flex items-center gap-3 text-sm">
            <Tag :value="`${candidates.length} total`" severity="secondary" />
            <Tag v-if="deletedDuplicateCount" :value="`${deletedDuplicateCount} deleted`" severity="danger" />
            <Tag v-if="duplicateCount - deletedDuplicateCount" :value="`${duplicateCount - deletedDuplicateCount} existing`" severity="warn" />
            <Tag :value="`${selectedCount} selected`" severity="info" />
          </div>
        </template>
        <template #end>
          <div class="flex gap-2">
            <Button @click="selectAll" label="Select All" severity="secondary" size="small" outlined :disabled="!candidates.length" />
            <Button @click="deselectAll" label="Deselect All" severity="secondary" size="small" outlined :disabled="!candidates.length" />
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
        </template>
      </Toolbar>

      <DataTable
        :value="sortedCandidates"
        v-model:selection="selectedModel"
        dataKey="id"
        scrollable
        scrollHeight="500px"
        size="small"
        stripedRows
        :rowClass="(data) => data.is_duplicate && data.existing_login_is_deleted ? 'bg-red-900/20' : ''"
      >
        <Column selectionMode="multiple" headerStyle="width: 3rem" />
        <Column header="Site">
          <template #body="{ data }">
            <div class="flex flex-col">
              <span>{{ data.name || data.domain }}</span>
              <span class="text-xs text-surface-400 truncate max-w-[200px]">{{ data.domain }}</span>
            </div>
          </template>
        </Column>
        <Column field="username" header="Username" />
        <Column header="Provider">
          <template #body="{ data }">
            <div class="flex flex-col gap-1">
              <span class="text-sm">{{ data.label || data.domain }}</span>
              <span v-if="!data.provider_key" class="text-xs text-orange-400">No match — will import as-is</span>
            </div>
          </template>
        </Column>
        <Column header="Status" style="width: 8rem">
          <template #body="{ data }">
            <Tag v-if="data.is_duplicate && data.existing_login_is_deleted" value="deleted" severity="danger" />
            <Tag v-else-if="data.is_duplicate" value="exists" severity="warn" />
            <Tag v-else value="new" severity="success" />
          </template>
        </Column>
      </DataTable>
    </div>
  </Section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import FileUpload from 'primevue/fileupload'
import Tag from 'primevue/tag'
import Toolbar from 'primevue/toolbar'
import Section from './Section.vue'

const props = defineProps({
  importSession: { type: Object, default: null },
  importing: { type: Boolean, default: false },
})

const emit = defineEmits(['upload', 'import', 'cancel'])

const selectedRows = ref([])

const selectedModel = computed({
  get: () => selectedRows.value,
  set: (val) => { selectedRows.value = val },
})

const candidates = computed(() => props.importSession?.candidates || [])

const sortedCandidates = computed(() => {
  const all = candidates.value
  const deletedDupes = all.filter(c => c.is_duplicate && c.existing_login_is_deleted)
  const regularDupes = all.filter(c => c.is_duplicate && !c.existing_login_is_deleted)
  const newOnes = all.filter(c => !c.is_duplicate)
  return [...deletedDupes, ...regularDupes, ...newOnes]
})

const duplicateCount = computed(() => {
  return candidates.value.filter(c => c.is_duplicate).length
})

const deletedDuplicateCount = computed(() => {
  return candidates.value.filter(c => c.is_duplicate && c.existing_login_is_deleted).length
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

watch(candidates, (newCandidates) => {
  selectedRows.value = newCandidates.filter(c => !c.is_duplicate || !c.existing_login_is_deleted)
}, { immediate: true })

function selectAll() {
  selectedRows.value = [...candidates.value]
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
  emit('cancel')
}
</script>
