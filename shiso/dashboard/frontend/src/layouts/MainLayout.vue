<template>
  <div class="min-h-screen bg-shiso-950 text-shiso-200">
    <Toast position="top-right" />
    <ConfirmDialog />

    <div class="flex h-screen">
      <nav class="w-56 bg-shiso-900 border-r border-shiso-800 overflow-y-auto flex-shrink-0">
        <div class="py-2">
          <div class="px-3 pt-3 pb-1 text-xs font-bold text-shiso-500 uppercase tracking-wider">Navigation</div>
          <RouterLink
            v-for="item in navItems"
            :key="item.to"
            :to="item.to"
            class="nav-link"
            active-class="nav-link--active"
          >
            {{ item.label }}
            <span v-if="item.count != null" class="text-xs text-shiso-500 ml-1">({{ item.count }})</span>
          </RouterLink>
        </div>
      </nav>

      <main class="flex-1 overflow-y-auto p-6">
        <RouterView />
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
    <RewardsDialog
      v-model:visible="rewardsDialogVisible"
      v-model:form="rewardsForm"
      :edit="rewardsDialogEdit"
      :accounts="accountsList"
      :logins="logins"
      :rewardTypes="rewardsTypes"
      @save="() => saveRewardsProgram(loadAll)"
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
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import Toast from 'primevue/toast'
import ConfirmDialog from 'primevue/confirmdialog'

import PromoDialog from '../components/PromoDialog.vue'
import RewardsDialog from '../components/RewardsDialog.vue'
import LoginDialog from '../components/LoginDialog.vue'
import InteractiveAuthDialog from '../components/InteractiveAuthDialog.vue'
import AgentHelpDialog from '../components/AgentHelpDialog.vue'

import { useDashboard } from '../composables/useDashboard.js'
import { useLogins } from '../composables/useLogins.js'
import { usePromos } from '../composables/usePromos.js'
import { useRewards } from '../composables/useRewards.js'
import { useInteractiveAuth } from '../composables/useInteractiveAuth.js'
import { useAgentSessions } from '../composables/useAgentSessions.js'

const { liabilityRows, assetRows, zeroBalanceRows, loadDashboard } = useDashboard()

const loginsComposed = useLogins()
const { logins, providers, accountTypes, toolOptions, loginDialogVisible, loginDialogEdit, loginForm, saveLogin } = loginsComposed
const { loadLogins, loadProviders } = loginsComposed

const promosComposed = usePromos()
const { promos, accountsList, promoDialogVisible, promoDialogEdit, promoForm, promoTypes, openPromoDialog, savePromo, confirmDeletePromo } = promosComposed
const { loadPromos } = promosComposed

const rewardsComposed = useRewards()
const { rewards, rewardsDialogVisible, rewardsDialogEdit, rewardsForm, rewardsTypes, openRewardsDialog, saveRewardsProgram } = rewardsComposed
const { loadRewards } = rewardsComposed

const iauthComposed = useInteractiveAuth({ reloadLogins: loadLogins })
const { interactiveAuthDialogVisible, interactiveAuthDialogLogin, interactiveAuthSession, interactiveAuthResponse, interactiveAuthResponding, closeInteractiveAuthDialog, submitInteractiveAuthResponse } = iauthComposed

const agentComposed = useAgentSessions()
const { agentDialogVisible, agentDialogSession, agentResponse, agentResponding, closeAgentDialog, submitAgentResponse } = agentComposed

const navItems = computed(() => [
  { to: '/overview', label: 'Overview' },
  { to: '/finances', label: 'Finances', count: liabilityRows.value.length + assetRows.value.length },
  { to: '/zero-balance', label: 'Zero Balance', count: zeroBalanceRows.value.length },
  { to: '/accounts', label: 'Accounts', count: logins.value.length },
  { to: '/import', label: 'Import' },
])

async function loadAll() {
  await Promise.all([loadDashboard(), loadLogins(), loadProviders(), loadPromos(), loadRewards()])
}

onMounted(loadAll)
</script>

<style scoped>
.nav-link {
  display: block;
  width: 100%;
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  color: #9ca3af;
  text-decoration: none;
  transition: color 0.15s, background-color 0.15s;
  border-left: 2px solid transparent;
}
.nav-link:hover {
  background-color: #1f2937;
  color: #f3f4f6;
}
.nav-link--active {
  background-color: #374151;
  color: #ffffff;
  border-left-color: #4ade80;
  font-weight: 500;
}
</style>
