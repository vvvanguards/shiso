<template>
  <div class="mx-auto max-w-7xl space-y-6">
    <ZeroBalanceSection
      :rows="zeroBalanceRows"
      v-model:filters="tableFilters"
      :logins="logins"
      @sync="(s) => dashboard.syncSnapshotRow(s, logins, syncLoginRow)"
      @edit="(s) => dashboard.editSnapshotRow(s, logins, openLoginDialog)"
    />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'

import ZeroBalanceSection from '../components/ZeroBalanceSection.vue'

import { useDashboard } from '../composables/useDashboard.js'
import { useLogins } from '../composables/useLogins.js'
import { usePromos } from '../composables/usePromos.js'

const dashboard = useDashboard()
const { tableFilters, zeroBalanceRows, loadDashboard } = dashboard

const { logins, loadLogins, syncLoginRow, openLoginDialog } = useLogins()

onMounted(() => Promise.all([loadDashboard(), loadLogins()]))
</script>
