<template>
  <Section header="Manage Logins" :collapsed="true" persistKey="logins">
    <template #icons>
      <Button @click.stop="emit('add')" icon="pi pi-plus" severity="success" size="small" text rounded />
      <Button
        @click.stop="emit('syncAll')"
        :loading="syncingAll"
        :disabled="!enabledCount"
        icon="pi pi-sync"
        severity="secondary"
        size="small"
        text
        rounded
        v-tooltip.top="'Sync all enabled'"
      />
    </template>

    <DataTable :value="logins" stripedRows size="small" :loading="loading" sortField="provider_key" :sortOrder="1" :rowClass="(data) => !data.enabled ? 'opacity-50' : ''">
      <Column header="Provider" sortField="provider_key" sortable>
        <template #body="{ data }">
          <div class="font-medium">{{ data.institution || data.provider_key }}</div>
          <div class="text-xs text-shiso-400">{{ data.label }}</div>
        </template>
      </Column>
      <Column field="account_type" header="Type" sortable>
        <template #body="{ data }">
          <Tag :value="data.account_type" :severity="typeSeverity(data.account_type)" />
        </template>
      </Column>
      <Column field="username" header="Username">
        <template #body="{ data }">
          <span class="text-sm">{{ data.username || '—' }}</span>
        </template>
      </Column>
      <Column header="Synced" sortField="last_sync_finished_at" sortable>
        <template #body="{ data }">
          <div class="flex items-center gap-1.5" v-tooltip.top="data.last_sync_error">
            <i :class="syncIcon(data)" />
            <span class="text-sm text-shiso-300">{{ syncTimestamp(data) }}</span>
          </div>
        </template>
      </Column>
      <Column header="" style="width: 8rem">
        <template #body="{ data }">
          <div class="flex gap-1">
            <Button @click="emit('sync', data)" icon="pi pi-sync" severity="success" text rounded size="small" :disabled="!data.enabled || data.last_sync_status === 'queued'" v-tooltip.top="'Sync now'" />
            <Button @click="emit('edit', data)" icon="pi pi-pencil" severity="secondary" text rounded size="small" v-tooltip.top="'Edit'" />
            <Button @click="emit('toggle', data)" :icon="data.enabled ? 'pi pi-pause' : 'pi pi-play'" severity="info" text rounded size="small" v-tooltip.top="data.enabled ? 'Pause' : 'Resume'" />
            <Button @click="emit('delete', data)" icon="pi pi-trash" severity="danger" text rounded size="small" v-tooltip.top="'Delete'" />
          </div>
        </template>
      </Column>
      <template #empty>
        <div class="py-6 text-center text-shiso-400">No logins configured.</div>
      </template>
    </DataTable>
  </Section>
</template>

<script setup>
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Tag from 'primevue/tag'
import Section from './Section.vue'
import { relativeTime, typeSeverity } from '../helpers.js'

const props = defineProps({
  logins: { type: Array, required: true },
  loading: { type: Boolean, default: false },
  syncingAll: { type: Boolean, default: false },
  enabledCount: { type: Number, default: 0 },
})

const emit = defineEmits(['add', 'syncAll', 'sync', 'edit', 'toggle', 'delete'])

function syncIcon(login) {
  if (login.last_auth_status === 'needs_2fa') return 'pi pi-exclamation-triangle text-accent-amber'
  if (login.last_auth_status === 'login_failed') return 'pi pi-times-circle text-accent-red'
  const s = login.last_sync_status
  if (!s) return 'pi pi-minus-circle text-shiso-500'
  if (s === 'queued' || s === 'running') return 'pi pi-spin pi-spinner text-blue-400'
  if (s === 'succeeded') return 'pi pi-check-circle text-accent-green'
  return 'pi pi-times-circle text-accent-red'
}

function syncTimestamp(login) {
  const ts = login.last_sync_finished_at || login.last_sync_started_at
  if (!ts) return 'Never'
  return relativeTime(ts)
}
</script>