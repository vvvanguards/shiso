<template>
  <DataTable :value="rows" stripedRows size="small" :sortField="sortField" :sortOrder="sortOrder"
    v-model:filters="filtersModel" :globalFilterFields="globalFilterFields">
    <Column header="Account" sortField="display_name" sortable>
      <template #body="{ data }">
        <div class="font-medium">{{ data.display_name || data.address || 'Unnamed' }}</div>
        <div class="text-xs text-shiso-400">{{ data.account_mask ? '••' + data.account_mask : '' }}</div>
      </template>
    </Column>

    <Column field="institution" header="Provider" sortable>
      <template #body="{ data }">
        <span class="text-sm">{{ data.institution }}</span>
      </template>
    </Column>

    <Column field="account_subcategory" header="Type" sortable>
      <template #body="{ data }">
        <Tag :value="data.account_subcategory || 'Other'" :severity="typeSeverity(data.account_subcategory)" />
      </template>
    </Column>

    <Column field="current_balance" header="Balance" sortable>
      <template #body="{ data }">
        <span class="font-medium" :class="balanceColor">{{ money(data.current_balance) }}</span>
        <div v-if="data.credit_limit" class="text-xs text-shiso-400">of {{ money(data.credit_limit) }}</div>
      </template>
    </Column>

    <!-- Extra columns injected by parent -->
    <slot />

    <Column v-if="showActions" header="" style="width: 6rem">
      <template #body="{ data }">
        <div class="flex justify-end gap-1">
          <Button
            icon="pi pi-sync"
            severity="success"
            text
            rounded
            size="small"
            :disabled="!canSync(data)"
            v-tooltip.top="'Sync linked login'"
            @click="emit('sync', data)"
          />
          <Button
            icon="pi pi-pencil"
            severity="secondary"
            text
            rounded
            size="small"
            :disabled="!canEdit(data)"
            v-tooltip.top="'Edit linked login'"
            @click="emit('edit', data)"
          />
        </div>
      </template>
    </Column>

    <Column field="captured_at" header="Updated" sortable>
      <template #body="{ data }">
        <span class="text-shiso-400 text-xs">{{ relativeTime(data.captured_at) }}</span>
      </template>
    </Column>

    <template #empty>
      <div class="py-6 text-center text-shiso-400">{{ emptyMessage }}</div>
    </template>
  </DataTable>
</template>

<script setup>
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Tag from 'primevue/tag'
import { money, relativeTime, typeSeverity } from '../helpers.js'

const props = defineProps({
  rows: { type: Array, required: true },
  sortField: { type: String, default: 'current_balance' },
  sortOrder: { type: Number, default: -1 },
  balanceColor: { type: String, default: 'text-accent-amber' },
  emptyMessage: { type: String, default: 'No accounts found.' },
  showActions: { type: Boolean, default: false },
  logins: { type: Array, default: () => [] },
})

const emit = defineEmits(['sync', 'edit'])

const filtersModel = defineModel('filters', { type: Object, required: true })

const globalFilterFields = ['display_name', 'institution', 'provider_key', 'account_subcategory', 'address']

function linkedLogin(row) {
  if (!row.scraper_login_id) return null
  return props.logins.find(l => l.id === row.scraper_login_id) || null
}

function canSync(row) {
  const login = linkedLogin(row)
  return !!(login && login.enabled && !['queued', 'running'].includes(login.last_sync_status))
}

function canEdit(row) {
  return !!linkedLogin(row)
}
</script>
