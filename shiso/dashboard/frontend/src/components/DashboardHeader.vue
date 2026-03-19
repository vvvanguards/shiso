<template>
  <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
    <div class="flex items-center gap-2">
      <img src="/shiso-icon-64.png" alt="Shiso" class="h-8 w-8" />
      <h1 class="display-font text-3xl font-semibold">Shiso</h1>
    </div>
    <div class="flex flex-wrap gap-2">
      <Button @click="$emit('refresh')" :loading="loading" label="Refresh" icon="pi pi-refresh" severity="secondary" size="small" outlined />
      <Button @click="$emit('sync-all')" :loading="syncingAllLogins" :label="syncingAllLogins ? 'Syncing…' : 'Sync All'" icon="pi pi-sync" severity="success" size="small" />
    </div>
  </div>
</template>

<script setup>
import Button from 'primevue/button'

defineProps({
  loading: Boolean,
  syncingAllLogins: Boolean,
})

defineEmits(['refresh', 'sync-all'])
</script>
