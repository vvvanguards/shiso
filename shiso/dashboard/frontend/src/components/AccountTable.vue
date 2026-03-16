<template>
  <DataTable :value="rows" stripedRows size="small" :sortField="sortField" :sortOrder="sortOrder"
    v-model:filters="filtersModel" :globalFilterFields="globalFilterFields">
    <Column header="Account" sortField="display_name" sortable>
      <template #body="{ data }">
        <div class="font-medium">{{ data.display_name || data.address || 'Unnamed' }}</div>
        <div class="text-xs text-surface-400">{{ data.account_mask ? '••' + data.account_mask : '' }}</div>
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
        <div v-if="data.credit_limit" class="text-xs text-surface-400">of {{ money(data.credit_limit) }}</div>
      </template>
    </Column>

    <!-- Extra columns injected by parent -->
    <slot />

    <Column field="captured_at" header="Updated" sortable>
      <template #body="{ data }">
        <span class="text-surface-400 text-xs">{{ relativeTime(data.captured_at) }}</span>
      </template>
    </Column>

    <template #empty>
      <div class="py-6 text-center text-surface-400">{{ emptyMessage }}</div>
    </template>
  </DataTable>
</template>

<script setup>
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Tag from 'primevue/tag'
import { money, relativeTime, typeSeverity } from '../helpers.js'

defineProps({
  rows: { type: Array, required: true },
  sortField: { type: String, default: 'current_balance' },
  sortOrder: { type: Number, default: -1 },
  balanceColor: { type: String, default: 'text-amber-400' },
  emptyMessage: { type: String, default: 'No accounts found.' },
})

const filtersModel = defineModel('filters', { type: Object, required: true })

const globalFilterFields = ['display_name', 'institution', 'provider_key', 'account_subcategory', 'address']
</script>
