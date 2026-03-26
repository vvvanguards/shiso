<template>
  <div class="mx-auto max-w-7xl space-y-6">
    <DashboardHeader :loading="loading" :syncingAllLogins="syncingAllLogins" @refresh="loadAll" @sync-all="syncEnabledLogins" />

    <Message v-if="statusMessage" :severity="statusError ? 'error' : 'success'" :closable="true" @close="statusMessage = ''">
      {{ statusMessage }}
    </Message>

    <SummaryCards :summary="summary" />

    <ProblemLoginsAlert :problemLogins="problemLoginsDerived" :authLoading="interactiveAuthLoading" @resolve="startInteractiveAuthForLogin" />

    <AgentHelpBanner :sessions="activeSessions" @respond="openAgentDialog" />

    <GlobalSearch v-model="tableFilters['global'].value" />
  </div>
</template>

<script setup>
import Message from 'primevue/message'

import DashboardHeader from '../components/DashboardHeader.vue'
import SummaryCards from '../components/SummaryCards.vue'
import ProblemLoginsAlert from '../components/ProblemLoginsAlert.vue'
import AgentHelpBanner from '../components/AgentHelpBanner.vue'
import GlobalSearch from '../components/GlobalSearch.vue'

import { useDashboard } from '../composables/useDashboard.js'
import { useLogins } from '../composables/useLogins.js'
import { useInteractiveAuth } from '../composables/useInteractiveAuth.js'
import { useAgentSessions } from '../composables/useAgentSessions.js'

const { summary, loading, statusMessage, statusError, tableFilters, loadDashboard } = useDashboard()
const { syncingAllLogins, problemLoginsDerived, loadLogins, loadProviders, syncEnabledLogins } = useLogins()
const { interactiveAuthLoading, startInteractiveAuthForLogin } = useInteractiveAuth({ reloadLogins: loadLogins })
const { activeSessions, openAgentDialog } = useAgentSessions()

async function loadAll() {
  loading.value = true
  statusMessage.value = ''
  statusError.value = false
  try {
    await Promise.all([loadDashboard(), loadLogins(), loadProviders()])
  } catch (err) {
    statusMessage.value = err.message
    statusError.value = true
  } finally {
    loading.value = false
  }
}
</script>
