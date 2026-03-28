<template>
  <div class="min-h-screen bg-shiso-950 text-shiso-200">
    <Toast position="top-right" />
    <ConfirmDialog />

    <div class="flex h-screen">
      <nav class="w-56 bg-shiso-900 border-r border-shiso-800 overflow-y-auto flex-shrink-0">
        <div class="py-2">
          <button
            @click="scrollToSection('overview')"
            :class="[
              'w-full text-left px-4 py-2 text-sm font-semibold transition-colors border-l-2',
              activeSection === 'overview'
                ? 'bg-shiso-700 text-white border-shiso-400'
                : 'text-shiso-300 hover:bg-shiso-800 hover:text-white border-transparent'
            ]"
          >
            Overview
          </button>

          <div class="h-px bg-shiso-800 my-2" />

          <template v-for="group in sidebarTree" :key="group.name">
            <div class="px-3 pt-3 pb-1 text-xs font-bold text-shiso-500 uppercase tracking-wider">
              {{ group.name }}
            </div>
            <template v-for="section in group.items" :key="section.id">
              <button
                v-if="!section.children"
                @click="scrollToSection(section.id)"
                :class="[
                  'w-full text-left px-4 py-1.5 text-sm transition-colors rounded',
                  activeSection === section.id
                    ? 'bg-shiso-700 text-white font-medium'
                    : 'text-shiso-400 hover:bg-shiso-800 hover:text-shiso-100'
                ]"
              >
                {{ section.label }}
                <span v-if="section.count != null" class="text-xs text-shiso-500 ml-1">({{ section.count }})</span>
              </button>
              <template v-else>
                <button
                  @click="scrollToSection(section.id)"
                  :class="[
                    'w-full text-left px-4 py-1.5 text-sm font-medium transition-colors rounded flex items-center',
                    activeSection === section.id
                      ? 'text-white'
                      : 'text-shiso-300 hover:text-white'
                  ]"
                >
                  <span>{{ section.label }}</span>
                  <span v-if="section.count != null" class="text-xs text-shiso-500 ml-1">({{ section.count }})</span>
                </button>
                <div class="ml-6 mt-1 space-y-0.5">
                  <button
                    v-for="child in section.children"
                    :key="child.id"
                    @click="scrollToSection(child.id)"
                    :class="[
                      'w-full text-left px-3 py-1.5 text-sm transition-colors rounded',
                      activeSection === child.id
                        ? 'bg-shiso-600 text-white font-medium'
                        : 'text-shiso-400 hover:bg-shiso-700 hover:text-shiso-100'
                    ]"
                  >
                    {{ child.label }}
                    <span v-if="child.count != null" class="text-xs text-shiso-500 ml-1">({{ child.count }})</span>
                  </button>
                </div>
              </template>
            </template>
          </template>
        </div>
      </nav>

      <main ref="mainRef" class="flex-1 overflow-y-auto p-6">
        <div class="mx-auto max-w-7xl space-y-6">
          <section id="overview">
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
          </section>

          <section id="liabilities">
            <LiabilitiesSection
              :rows="liabilityRows"
              v-model:filters="tableFilters"
              :logins="logins"
              @sync="handleSnapshotSync"
              @edit="handleSnapshotEdit"
            />
          </section>

          <section id="bills">
            <BillsSection
              :rows="billRows"
              v-model:filters="tableFilters"
              :logins="logins"
              @sync="handleSnapshotSync"
              @edit="handleSnapshotEdit"
              @toggle-paid="handleTogglePaid"
            />
          </section>

          <section id="promos">
            <PromosPanel
              :promos="promos"
              :loading="loading"
              @add="openPromoDialog"
              @edit="openPromoDialog"
              @delete="confirmDeletePromo($event, loadAll)"
            />
          </section>

          <section id="assets">
            <AssetsSection
              :rows="assetRows"
              v-model:filters="tableFilters"
              :logins="logins"
              @sync="handleSnapshotSync"
              @edit="handleSnapshotEdit"
            />
            <RewardsSection
              :rows="rewards"
              @add="openRewardsDialog"
              @edit="openRewardsDialog"
            />
          </section>

          <section id="zero-balance">
            <ZeroBalanceSection
              :rows="zeroBalanceRows"
              v-model:filters="tableFilters"
              :logins="logins"
              @sync="handleSnapshotSync"
              @edit="handleSnapshotEdit"
            />
          </section>

          <section id="logins">
            <LoginsPanel
              :logins="logins"
              :loading="loginsLoading"
              :syncingAll="syncingAllLogins"
              :enabledCount="enabledLoginCount"
              :showDeleted="showDeleted"
              @add="openLoginDialog()"
              @syncAll="syncEnabledLogins"
              @sync="syncLoginRow"
              @edit="openLoginDialog"
              @toggle="toggleEnabled"
              @delete="confirmDeleteLogin"
              @toggleShowDeleted="showDeleted = !showDeleted; loadLogins()"
            />
          </section>

          <section id="import">
            <ImportPanel
              :importSession="importSession"
              :importing="importing"
              @upload="handleFileUpload"
              @import="(ids) => runImportFromSelection(ids, loadLogins)"
              @cancel="cancelImport"
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
      :logins="logins"
      :rewardTypes="rewardsTypes"
      @save="() => saveRewardsProgram(loadAll)"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

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
import RewardsSection from './components/RewardsSection.vue'
import LoginsPanel from './components/LoginsPanel.vue'
import ImportPanel from './components/ImportPanel.vue'
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

const mainRef = ref(null)
const activeSection = provideActiveSection('overview')

const {
  summary, loading, statusMessage, statusError, tableFilters,
  billRows, assetRows, liabilityRows, zeroBalanceRows,
  loadDashboard, toggleSnapshotPaidStatus,
} = useDashboard()

const {
  logins, loginsLoading, syncingAllLogins, showDeleted, providers, accountTypes,
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
  importSession, importing,
  handleFileUpload, runImportFromSelection, cancelImport,
} = useImport()

const sidebarTree = computed(() => [
  {
    name: 'Finances',
    items: [
      { id: 'liabilities', label: 'Liabilities', count: liabilityRows.value.length, children: [
        { id: 'promos', label: 'Promo APRs', count: promos.value.length },
        { id: 'bills', label: 'Bills', count: billRows.value.length },
      ]},
      { id: 'assets', label: 'Assets', count: assetRows.value.length, children: [
        { id: 'rewards', label: 'Rewards', count: rewards.value.length },
      ]},
    ]
  },
  {
    name: 'Status',
    items: [
      { id: 'zero-balance', label: 'Zero Balance', count: zeroBalanceRows.value.length },
    ]
  },
  {
    name: 'Accounts',
    items: [
      { id: 'logins', label: 'Logins', count: logins.value.length },
      { id: 'import', label: 'Import' },
    ]
  },
])

function scrollToSection(id) {
  activeSection.value = id
}

watch(activeSection, (sectionId) => {
  if (!sectionId || !mainRef.value) return
  requestAnimationFrame(() => {
    const el = mainRef.value.querySelector('#' + sectionId)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  })
})

function handleSnapshotSync(snapshot) {
  const login = logins.value.find(l => l.id === snapshot.scraper_login_id)
  if (!login) {
    return
  }
  const accountFilter = snapshot.address || snapshot.account_mask || snapshot.display_name || null
  const accountLabel = snapshot.display_name || snapshot.account_mask || 'Account'
  syncLoginRow(login, accountFilter ? { account_filter: accountFilter } : null, `${accountLabel} queued for sync`)
}

function handleSnapshotEdit(snapshot) {
  const login = logins.value.find(l => l.id === snapshot.scraper_login_id)
  if (!login) {
    return
  }
  openLoginDialog(login)
}

function handleTogglePaid(snapshotId, newIsPaid) {
  toggleSnapshotPaidStatus(snapshotId, newIsPaid)
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
  agentSessionsPollTimer = setInterval(loadActiveSessions, 5000)
})
onUnmounted(() => {
  stopInteractiveAuthPolling()
  stopAgentPolling()
  if (agentSessionsPollTimer) clearInterval(agentSessionsPollTimer)
})
</script>
