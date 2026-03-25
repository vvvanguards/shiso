<template>
  <Dialog v-model:visible="visible" :header="edit ? 'Edit Rewards Program' : 'Add Rewards Program'" modal :style="{ width: '480px' }">
    <div class="flex flex-col gap-4 pt-2">
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Scraper Login *</label>
        <Select v-model="form.scraper_login_id" :options="logins" optionLabel="label" optionValue="id" placeholder="Select login" fluid />
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Linked Account (optional)</label>
        <Select v-model="form.financial_account_id" :options="accounts" optionLabel="label" optionValue="id" placeholder="Select account (optional)" fluid />
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Program Name</label>
        <InputText v-model="form.program_name" placeholder="e.g. Chase Ultimate Rewards" fluid />
      </div>
      <div class="grid grid-cols-2 gap-4">
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium">Type</label>
          <Select v-model="form.program_type" :options="rewardTypes" optionLabel="label" optionValue="value" fluid />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium">Membership ID</label>
          <InputText v-model="form.membership_id" placeholder="Loyalty number (optional)" fluid />
        </div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Unit Name</label>
        <InputText v-model="form.unit_name" placeholder="points, miles, %" fluid />
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Cents per Unit (for valuation)</label>
        <InputText v-model="form.cents_per_unit" type="number" step="0.01" placeholder="e.g. 1.5 for 1.5¢/point" fluid />
      </div>
    </div>
    <template #footer>
      <Button @click="visible = false" label="Cancel" severity="secondary" text />
      <Button @click="emit('save')" :label="edit ? 'Update' : 'Create'" severity="success" />
    </template>
  </Dialog>
</template>

<script setup>
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'

defineProps({
  edit: { type: Boolean, default: false },
  accounts: { type: Array, default: () => [] },
  logins: { type: Array, default: () => [] },
  rewardTypes: { type: Array, default: () => [] },
})

const visible = defineModel('visible', { type: Boolean, required: true })
const form = defineModel('form', { type: Object, required: true })

const emit = defineEmits(['save'])
</script>
