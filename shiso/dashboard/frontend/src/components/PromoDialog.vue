<template>
  <Dialog v-model:visible="visible" :header="edit ? 'Edit Promo Period' : 'Add Promo Period'" modal :style="{ width: '480px' }">
    <div class="flex flex-col gap-4 pt-2">
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Account</label>
        <Select v-model="form.financial_account_id" :options="accounts" optionLabel="label" optionValue="id" placeholder="Select account" fluid />
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Promo Type</label>
        <Select v-model="form.promo_type" :options="promoTypes" optionLabel="label" optionValue="value" fluid />
      </div>
      <div class="grid grid-cols-2 gap-4">
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium">Promo APR %</label>
          <InputText v-model="form.apr_rate" type="number" step="0.01" fluid />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium">Regular APR %</label>
          <InputText v-model="form.regular_apr" type="number" step="0.01" placeholder="Optional" fluid />
        </div>
      </div>
      <div class="grid grid-cols-2 gap-4">
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium">Start Date</label>
          <InputText v-model="form.start_date" type="date" fluid />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium">End Date</label>
          <InputText v-model="form.end_date" type="date" fluid />
        </div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Original Amount</label>
        <InputText v-model="form.original_amount" type="number" step="0.01" placeholder="Optional" fluid />
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Description</label>
        <InputText v-model="form.description" placeholder="Optional note" fluid />
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
  promoTypes: { type: Array, default: () => [] },
})

const visible = defineModel('visible', { type: Boolean, required: true })
const form = defineModel('form', { type: Object, required: true })

const emit = defineEmits(['save'])
</script>
