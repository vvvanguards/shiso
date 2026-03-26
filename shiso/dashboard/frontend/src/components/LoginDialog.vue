<template>
  <Dialog v-model:visible="visible" :header="edit ? 'Edit Login' : 'Add Login'" modal :style="{ width: '480px' }">
    <div class="flex flex-col gap-4 pt-2">
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Provider Key <span class="text-red-400">*</span></label>
        <AutoComplete v-model="form.provider_key" :suggestions="filteredProviders" @complete="searchProviders" placeholder="e.g. amex" fluid />
        <small v-if="errors.provider_key" class="text-red-400">{{ errors.provider_key }}</small>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Institution</label>
        <InputText v-model="form.institution" placeholder="e.g. Bank of America" fluid />
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Label <span class="text-red-400">*</span></label>
        <InputText v-model="form.label" placeholder="Display label" fluid />
        <small v-if="errors.label" class="text-red-400">{{ errors.label }}</small>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Account Type</label>
        <Select v-model="form.account_type" :options="accountTypes" fluid />
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Tool</label>
        <Select v-model="form.tool_key" :options="toolOptions" optionLabel="label" optionValue="value" fluid />
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Username <span class="text-red-400">*</span></label>
        <InputText v-model="form.username" placeholder="Username" fluid />
        <small v-if="errors.username" class="text-red-400">{{ errors.username }}</small>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Password</label>
        <Password v-model="form.password" :placeholder="edit ? '(unchanged)' : 'Password'" toggleMask :feedback="false" fluid />
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Login URL</label>
        <InputText v-model="form.login_url" placeholder="https://..." fluid />
      </div>
      <div class="flex items-center gap-2">
        <ToggleSwitch v-model="form.enabled" />
        <label class="text-sm">Enabled</label>
      </div>
    </div>
    <template #footer>
      <Button @click="visible = false" label="Cancel" severity="secondary" text />
      <Button @click="handleSave" :label="edit ? 'Update' : 'Create'" severity="success" />
    </template>
  </Dialog>
</template>

<script setup>
import { ref } from 'vue'

import AutoComplete from 'primevue/autocomplete'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Password from 'primevue/password'
import Select from 'primevue/select'
import ToggleSwitch from 'primevue/toggleswitch'

const props = defineProps({
  edit: { type: Boolean, default: false },
  providers: { type: Array, default: () => [] },
  accountTypes: { type: Array, default: () => [] },
  toolOptions: { type: Array, default: () => [] },
})

const visible = defineModel('visible', { type: Boolean, required: true })
const form = defineModel('form', { type: Object, required: true })

const emit = defineEmits(['save'])

const filteredProviders = ref([])
const errors = ref({})

function searchProviders(event) {
  const query = String(event.query || '').toLowerCase()
  filteredProviders.value = props.providers.filter(provider => provider.toLowerCase().includes(query))
}

function validate() {
  errors.value = {}
  if (!form.value.provider_key?.trim()) {
    errors.value.provider_key = 'Provider key is required'
  }
  if (!form.value.label?.trim()) {
    errors.value.label = 'Label is required'
  }
  if (!form.value.username?.trim()) {
    errors.value.username = 'Username is required'
  }
  return Object.keys(errors.value).length === 0
}

function handleSave() {
  if (validate()) {
    emit('save')
  }
}
</script>
