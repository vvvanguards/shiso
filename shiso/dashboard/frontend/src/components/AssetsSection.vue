<template>
  <Section header="Assets" :count="rows.length" persistKey="assets">
    <AccountTable
      :rows="rows"
      v-model:filters="filtersModel"
      balanceColor="text-accent-green"
      emptyMessage="No asset accounts found."
      showActions
      :canSyncRow="canSyncRow"
      :canEditRow="canEditRow"
      @sync="$emit('sync', $event)"
      @edit="$emit('edit', $event)"
    />
  </Section>
</template>

<script setup>
import Section from './Section.vue'
import AccountTable from './AccountTable.vue'

defineProps({
  rows: { type: Array, required: true },
  canSyncRow: { type: Function, required: true },
  canEditRow: { type: Function, required: true },
})

const filtersModel = defineModel('filters', { type: Object, required: true })

defineEmits(['sync', 'edit'])
</script>
