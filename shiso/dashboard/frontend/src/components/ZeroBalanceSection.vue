<template>
  <Section v-if="rows.length" header="Zero Balance" :count="rows.length" :collapsed="true" persistKey="zero-balance">
    <AccountTable
      :rows="rows"
      v-model:filters="filtersModel"
      balanceColor="text-shiso-300"
      emptyMessage="No zero-balance accounts found."
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
