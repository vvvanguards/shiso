<template>
  <Section v-if="promos.length || !loading" header="Promo APR Periods" :count="promos.length" persistKey="promos">
    <template #icons>
      <Button @click.stop="emit('add')" icon="pi pi-plus" severity="success" size="small" text rounded v-tooltip.top="'Add promo period'" />
    </template>
    <DataTable :value="promos" stripedRows size="small" sortField="end_date" :sortOrder="1" v-if="promos.length">
      <Column header="Account">
        <template #body="{ data }">
          <div class="font-medium">{{ data.account_display_name || data.account_institution }}</div>
          <div v-if="data.account_mask" class="text-xs text-surface-400">••{{ data.account_mask }}</div>
        </template>
      </Column>
      <Column field="promo_type" header="Type" sortable>
        <template #body="{ data }">
          <Tag :value="promoTypeLabel(data.promo_type)" :severity="promoTypeSeverity(data.promo_type)" />
        </template>
      </Column>
      <Column field="apr_rate" header="Promo APR" sortable>
        <template #body="{ data }">
          <span class="font-semibold text-green-400">{{ data.apr_rate }}%</span>
        </template>
      </Column>
      <Column field="end_date" header="Expires" sortable>
        <template #body="{ data }">
          <span :class="promoUrgencyClass(data.days_remaining)">{{ data.end_date }}</span>
          <div class="text-xs" :class="promoUrgencyClass(data.days_remaining)">
            {{ data.days_remaining > 0 ? `${data.days_remaining} days left` : 'Expired' }}
          </div>
        </template>
      </Column>
      <Column field="original_amount" header="Amount">
        <template #body="{ data }">{{ data.original_amount ? money(data.original_amount) : '—' }}</template>
      </Column>
      <Column field="regular_apr" header="Regular APR">
        <template #body="{ data }">
          <span v-if="data.regular_apr != null" class="text-amber-400">{{ data.regular_apr }}%</span>
          <span v-else class="text-surface-500">—</span>
        </template>
      </Column>
      <Column header="" style="width: 6rem">
        <template #body="{ data }">
          <div class="flex gap-1">
            <Button @click="emit('edit', data)" icon="pi pi-pencil" severity="secondary" text rounded size="small" v-tooltip.top="'Edit promo'" />
            <Button @click="emit('delete', data)" icon="pi pi-trash" severity="danger" text rounded size="small" v-tooltip.top="'Delete promo'" />
          </div>
        </template>
      </Column>
      <template #empty>
        <div class="py-6 text-center text-surface-400">No promo periods tracked.</div>
      </template>
    </DataTable>
    <div v-else class="py-4 text-center text-surface-400">
      No promo periods tracked. <Button @click="emit('add')" label="Add one" severity="secondary" size="small" text />
    </div>
  </Section>
</template>

<script setup>
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Tag from 'primevue/tag'
import Section from './Section.vue'
import { money } from '../helpers.js'

const props = defineProps({
  promos: { type: Array, required: true },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['add', 'edit', 'delete'])

function promoTypeLabel(type) {
  return ({ purchase: 'Purchase', balance_transfer: 'Balance Transfer', general: 'General' })[type] || type
}

function promoTypeSeverity(type) {
  return ({ purchase: 'info', balance_transfer: 'warn', general: 'secondary' })[type] || 'secondary'
}

function promoUrgencyClass(daysRemaining) {
  if (daysRemaining <= 0) return 'text-red-400 font-semibold'
  if (daysRemaining <= 30) return 'text-red-400 font-semibold'
  if (daysRemaining <= 90) return 'text-amber-400'
  return ''
}
</script>