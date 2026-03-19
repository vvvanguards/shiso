<template>
  <div class="min-h-screen bg-shiso-950 text-shiso-200">
    <Toast position="top-right" />
    <ConfirmDialog />

    <div class="flex h-screen">
      <nav class="w-56 bg-shiso-900 border-r border-shiso-800 p-4 overflow-y-auto flex-shrink-0">
        <div class="space-y-1">
          <button
            v-for="section in sections"
            :key="section.id"
            @click="scrollToSection(section.id)"
            :class="[
              'w-full text-left px-3 py-2 rounded text-sm transition-colors',
              activeSection === section.id
                ? 'bg-shiso-700 text-white'
                : 'text-shiso-400 hover:bg-shiso-800 hover:text-shiso-200'
            ]"
          >
            {{ section.label }}
            <span v-if="section.count != null" class="text-xs text-shiso-500 ml-1">({{ section.count }})</span>
          </button>
        </div>
      </nav>

      <main class="flex-1 overflow-y-auto p-6">
        <div class="mx-auto max-w-7xl space-y-6">
          <DashboardHeader
            :loading="loading"
            :syncingAllLogins="syncingAllLogins"
            @refresh="loadAll"
            @sync-all="syncEnabledLogins"
          />

          <Message v-if="statusMessage" :severity="statusError ? 'error' : 'success'" :closable="true" @close="statusMessage = ''">
            {{ statusMessage }}
          </Message>

          <SummaryCards :summary="summary" />

          <ProblemLoginsAlert
            :problemLogins="problemLoginsDerived"
            :authLoading="interactiveAuthLoading"
            @resolve="startInteractiveAuthForLogin"
          />

          <AgentHelpBanner
            :sessions="activeSessions"
            @respond="openAgentDialog"
          />

          <GlobalSearch v-model="tableFilters['global'].value" />

          <section id="promos">
            <PromosPanel :promos="promos" :loading="loading" @add="openPromoDialog()" @edit="openPromoDialog($event)" @delete="confirmDeletePromo($event, loadAll)" />
          </section>

          <section id="rewards">
            <RewardsPanel :rewards="rewards" :loading="loading" @add="openRewardsDialog()" @edit="openRewardsDialog($event)" />
          </section>

          <section id="bills">
            <BillsSection
              :rows="billRows"
              v-model:filters="tableFilters"
              :logins="logins"
              @sync="syncSnapshotRow($event, logins, syncLoginRow)"
              @edit="editSnapshotRow($event, logins, openLoginDialog)"
            />
          </section>

          <section id="assets">
            <AssetsSection
              :rows="assetRows"
              v-model:filters="tableFilters"
              :logins="logins"
              @sync="syncSnapshotRow($event, logins, syncLoginRow)"
              @edit="editSnapshotRow($event, logins, openLoginDialog)"
            />
          </section>

          <section id="liabilities">
            <LiabilitiesSection
              :rows="liabilityRows"
              v-model:filters="tableFilters"
              :logins="logins"
              @sync="syncSnapshotRow($event, logins, syncLoginRow)"
              @edit="editSnapshotRow($event, logins, openLoginDialog)"
            />
          </section>

          <section id="zero-balance">
            <ZeroBalanceSection
              :rows="zeroBalanceRows"
              v-model:filters="tableFilters"
              :logins="logins"
              @sync="syncSnapshotRow($event, logins, syncLoginRow)"
              @edit="editSnapshotRow($event, logins, openLoginDialog)"
            />
          </section>

          <section id="tools">
            <ToolsPanel />
          </section>

          <section id="logins">
            <LoginsPanel
              :logins="logins"
              :loading="loginsLoading"
              :syncingAll="syncingAllLogins"
              :enabledCount="enabledLoginCount"
              @add="openLoginDialog()"
              @syncAll="syncEnabledLogins"
              @sync="syncLoginRow"
              @edit="openLoginDialog"
              @toggle="toggleEnabled"
              @delete="confirmDeleteLogin"
            />
          </section>

          <section id="import">
            <ImportPanel
              :previewData="importPreviewData"
              :importing="importing"
              @upload="handleFileUpload"
              @import="(rows) => runImportFromSelection(rows, loadLogins)"
              @clear="clearImport"
            />
          </section>
        </div>
      </main>
    </div>

    <PromoDialog
      v-model:visible="promoDialogVisible"
      v-model:form="promoForm"
      :edit="promoDialogEdit"
      :accounts="accountsList"
      :promoTypes="promoTypes"
      @save="() => savePromo(loadAll)"
    />

    <InteractiveAuthDialog
      v-model:visible="interactiveAuthDialogVisible"
      v-model:response="interactiveAuthResponse"
      :login="interactiveAuthDialogLogin"
      :session="interactiveAuthSession"
      :responding="interactiveAuthResponding"
      @hide="closeInteractiveAuthDialog"
      @submit="submitInteractiveAuthResponse"
    />

    <AgentHelpDialog
      v-model:visible="agentDialogVisible"
      v-model:response="agentResponse"
      :session="agentDialogSession"
      :responding="agentResponding"
      @hide="closeAgentDialog"
      @submit="submitAgentResponse"
    />

    <LoginDialog
      v-model:visible="loginDialogVisible"
      v-model:form="loginForm"
      :edit="loginDialogEdit"
      :providers="providers"
      :accountTypes="accountTypes"
      :toolOptions="toolOptions"
      @save="saveLogin"
    />

    <RewardsDialog
      v-model:visible="rewardsDialogVisible"
      v-model:form="rewardsForm"
      :edit="rewardsDialogEdit"
      :accounts="accountsList"
      :rewardTypes="rewardsTypes"
      @save="() => saveRewardsProgram(loadAll)"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'

import Toast from 'primevue/toast'
import ConfirmDialog from 'primevue/confirmdialog'
import Message from 'primevue/message'

import DashboardHeader from './components/DashboardHeader.vue'
import SummaryCards from './components/SummaryCards.vue'
import ProblemLoginsAlert from './components/ProblemLoginsAlert.vue'
import GlobalSearch from './components/GlobalSearch.vue'
import BillsSection from './components/BillsSection.vue'
import AssetsSection from './components/AssetsSection.vue'
import LiabilitiesSection from './components/LiabilitiesSection.vue'
import ZeroBalanceSection from './components/ZeroBalanceSection.vue'
import PromosPanel from './components/PromosPanel.vue'
import RewardsPanel from './components/RewardsPanel.vue'
import LoginsPanel from './components/LoginsPanel.vue'
import ImportPanel from './components/ImportPanel.vue'
import ToolsPanel from './components/ToolsPanel.vue'
import PromoDialog from './components/PromoDialog.vue'
import RewardsDialog from './components/RewardsDialog.vue'
import InteractiveAuthDialog from './components/InteractiveAuthDialog.vue'
import AgentHelpDialog from './components/AgentHelpDialog.vue'
import AgentHelpBanner from './components/AgentHelpBanner.vue'
import LoginDialog from './components/LoginDialog.vue'

import { useDashboard, provideActiveSection } from './composables/useDashboard.js'
import { useLogins } from './composables/useLogins.js'
import { useInteractiveAuth } from './composables/useInteractiveAuth.js'
import { useAgentSessions } from './composables/useAgentSessions.js'
import { usePromos } from './composables/usePromos.js'
import { useRewards } from './composables/useRewards.js'
import { useImport } from './composables/useImport.js'

const activeSection = provideActiveSection('bills')

const {
  summary, loading, statusMessage, statusError, tableFilters,
  billRows, assetRows, liabilityRows, zeroBalanceRows,
  canSyncSnapshotRow, canEditSnapshotRow, syncSnapshotRow, editSnapshotRow,
  loadDashboard,
} = useDashboard()

const {
  logins, loginsLoading, syncingAllLogins, providers, accountTypes,
  loginDialogVisible, loginDialogEdit, loginForm, toolOptions,
  problemLoginsDerived, enabledLoginCount,
  loadLogins, loadProviders, syncLoginRow, syncEnabledLogins,
  openLoginDialog, saveLogin, confirmDeleteLogin, toggleEnabled,
} = useLogins()

const {
  interactiveAuthLoading, interactiveAuthDialogVisible,
  interactiveAuthDialogLogin, interactiveAuthSession,
  interactiveAuthResponse, interactiveAuthResponding,
  stopInteractiveAuthPolling, closeInteractiveAuthDialog,
  startInteractiveAuthForLogin, submitInteractiveAuthResponse,
} = useInteractiveAuth({ reloadLogins: loadLogins })

const {
  activeSessions, agentDialogVisible, agentDialogSession,
  agentResponse, agentResponding,
  loadActiveSessions, openAgentDialog, closeAgentDialog,
  submitAgentResponse, stopPolling: stopAgentPolling,
} = useAgentSessions()

const {
  promos, accountsList, promoDialogVisible, promoDialogEdit, promoForm, promoTypes,
  loadPromos, openPromoDialog, savePromo, confirmDeletePromo,
} = usePromos()

const {
  rewards, rewardsDialogVisible, rewardsDialogEdit, rewardsForm, rewardsTypes,
  loadRewards, openRewardsDialog, saveRewardsProgram,
} = useRewards()

const {
  importPreviewData, importing,
  handleFileUpload, clearImport, runImportFromSelection,
} = useImport()

const sections = computed(() => [
  { id: 'promos', label: 'Promo APRs', count: promos.value.length },
  { id: 'rewards', label: 'Rewards', count: rewards.value.length },
  { id: 'bills', label: 'Bills', count: billRows.value.length },
  { id: 'assets', label: 'Assets', count: assetRows.value.length },
  { id: 'liabilities', label: 'Liabilities', count: liabilityRows.value.length },
  { id: 'zero-balance', label: 'Zero Balance', count: zeroBalanceRows.value.length },
  { id: 'tools', label: 'Tools' },
  { id: 'logins', label: 'Logins', count: logins.value.length },
  { id: 'import', label: 'Import' },
])

function scrollToSection(id) {
  activeSection.value = id
  const el = document.getElementById(id)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

async function loadAll() {
  loading.value = true
  statusMessage.value = ''
  statusError.value = false
  try {
    await Promise.all([
      loadDashboard(),
      loadLogins(),
      loadProviders(),
      loadPromos(),
      loadRewards(),
      loadActiveSessions(),
    ])
  } catch (err) {
    statusMessage.value = err.message
    statusError.value = true
  } finally {
    loading.value = false
  }
}

let agentSessionsPollTimer = null

onMounted(() => {
  loadAll()
  // Poll for agent sessions needing attention every 5s
  agentSessionsPollTimer = setInterval(loadActiveSessions, 5000)
})
onUnmounted(() => {
  stopInteractiveAuthPolling()
  stopAgentPolling()
  if (agentSessionsPollTimer) clearInterval(agentSessionsPollTimer)
})
</script>
