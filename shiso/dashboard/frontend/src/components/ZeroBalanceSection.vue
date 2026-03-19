<template>
  <Section v-if="rows.length" header="Zero Balance" :count="rows.length" :collapsed="true" persistKey="zero-balance">
    <AccountTable
      :rows="rows"
      v-model:filters="filtersModel"
      balanceColor="text-shiso-300"
      emptyMessage="No zero-balance accounts found."
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
