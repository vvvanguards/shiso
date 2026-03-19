<template>
  <div class="flex justify-end">
    <IconField>
      <InputIcon class="pi pi-search" />
      <InputText :modelValue="modelValue" @update:modelValue="$emit('update:modelValue', $event)" placeholder="Search all accounts..." size="small" />
    </IconField>
  </div>
</template>

<script setup>
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import InputText from 'primevue/inputtext'

defineProps({
  modelValue: { default: null },
})

defineEmits(['update:modelValue'])
</script>
