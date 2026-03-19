<template>
  <Section header="Assets" :count="rows.length" persistKey="assets">
    <AccountTable
      :rows="rows"
      v-model:filters="filtersModel"
      balanceColor="text-accent-green"
      emptyMessage="No asset accounts found."
      showActions
      :logins="logins"
      @sync="(s) => $emit('sync', s)"
      @edit="(s) => $emit('edit', s)"
    />
  </Section>
</template>

<script setup>
import Section from './Section.vue'
import AccountTable from './AccountTable.vue'

defineProps({
  rows: { type: Array, required: true },
  logins: { type: Array, required: true },
})

const filtersModel = defineModel('filters', { type: Object, required: true })

defineEmits(['sync', 'edit'])
</script>
