<template>
  <Section v-if="rewards.length || !loading" header="Rewards" :count="rewards.length" persistKey="rewards">
    <template #icons>
      <Button @click.stop="emit('add')" icon="pi pi-plus" severity="success" size="small" text rounded v-tooltip.top="'Add rewards program'" />
    </template>
    <DataTable :value="rewards" stripedRows size="small" sortField="program_type" :sortOrder="1" v-if="rewards.length">
      <Column header="Account">
        <template #body="{ data }">
          <div class="font-medium">{{ data.account_display_name || data.institution }}</div>
          <div v-if="data.account_mask" class="text-xs text-shiso-400">••{{ data.account_mask }}</div>
        </template>
      </Column>
      <Column field="program_name" header="Program" sortable>
        <template #body="{ data }">
          <div class="font-medium">{{ data.program_name }}</div>
          <div class="text-xs text-shiso-400">{{ data.program_type }}</div>
        </template>
      </Column>
      <Column field="balance" header="Balance" sortable>
        <template #body="{ data }">
          <span class="font-semibold">{{ formatRewardsBalance(data.balance, data.unit_name, data.program_type) }}</span>
          <div v-if="data.cents_per_unit" class="text-xs text-shiso-400">≈ ${{ formatMoney(data.monetary_value || 0) }}</div>
        </template>
      </Column>
      <Column field="monetary_value" header="Value" sortable>
        <template #body="{ data }">
          <span v-if="data.monetary_value != null" class="text-accent-green font-semibold">{{ money(data.monetary_value) }}</span>
          <span v-else class="text-shiso-500">—</span>
        </template>
      </Column>
      <Column header="" style="width: 4rem">
        <template #body="{ data }">
          <Button @click="emit('edit', data)" icon="pi pi-pencil" severity="secondary" text rounded size="small" v-tooltip.top="'Edit program'" />
        </template>
      </Column>
      <template #empty>
        <div class="py-6 text-center text-shiso-400">No rewards programs tracked.</div>
      </template>
    </DataTable>
    <div v-else class="py-4 text-center text-shiso-400">
      No rewards programs tracked. <Button @click="emit('add')" label="Add one" severity="secondary" size="small" text />
    </div>
  </Section>
</template>

<script setup>
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Section from './Section.vue'
import { money } from '../helpers.js'

const props = defineProps({
  rewards: { type: Array, required: true },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['add', 'edit'])

function formatRewardsBalance(balance, unitName, programType) {
  if (programType === 'cashback') {
    return `$${(balance || 0).toFixed(2)}`
  }
  const unit = unitName || (programType === 'miles' ? 'miles' : 'points')
  return `${(balance || 0).toLocaleString()} ${unit}`
}

function formatMoney(val) {
  return (val || 0).toFixed(2)
}
</script>