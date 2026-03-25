<template>
  <Section header="Bills" :count="rows.length" persistKey="bills">
    <AccountTable
      :rows="rows"
      v-model:filters="filtersModel"
      sortField="due_date"
      :sortOrder="1"
      emptyMessage="No bills with due dates found."
      showActions
      :logins="logins"
      @sync="$emit('sync', $event)"
      @edit="$emit('edit', $event)"
    >
      <Column field="is_paid" header="Paid" style="width: 5rem">
        <template #body="{ data }">
          <Checkbox
            :modelValue="data.is_paid"
            binary
            @update:modelValue="$emit('toggle-paid', data, $event)"
          />
        </template>
      </Column>
      <Column field="due_date" header="Due" sortable>
        <template #body="{ data }">
          <span :class="isDueSoon(data.due_date) ? 'text-accent-red font-semibold' : ''">{{ data.due_date || '—' }}</span>
        </template>
      </Column>
      <Column field="minimum_payment" header="Min Payment" sortable>
        <template #body="{ data }">{{ data.minimum_payment ? money(data.minimum_payment) : '—' }}</template>
      </Column>
      <Column field="interest_rate" header="APR" sortable>
        <template #body="{ data }">
          <span v-if="data.interest_rate != null">{{ data.interest_rate }}%</span>
          <span v-else class="text-shiso-500">—</span>
        </template>
      </Column>
      <Column field="autopay_enabled" header="Autopay" style="width: 5rem">
        <template #body="{ data }">
          <i v-if="data.autopay_enabled" class="pi pi-check text-green-500"></i>
          <span v-else class="text-surface-400">—</span>
        </template>
      </Column>
    </AccountTable>
  </Section>
</template>

<script setup>
import Checkbox from 'primevue/checkbox'
import Column from 'primevue/column'
import Section from './Section.vue'
import AccountTable from './AccountTable.vue'
import { money, isDueSoon } from '../helpers.js'

defineProps({
  rows: { type: Array, required: true },
  logins: { type: Array, required: true },
})

const filtersModel = defineModel('filters', { type: Object, required: true })

defineEmits(['sync', 'edit', 'toggle-paid'])
</script>
