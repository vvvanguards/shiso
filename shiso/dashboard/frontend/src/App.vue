<template>
  <div class="min-h-screen bg-surface-950 text-surface-0 p-6">
    <Toast position="top-right" />
    <ConfirmDialog />

    <div class="mx-auto max-w-7xl space-y-6">
      <!-- Header -->
      <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div class="flex items-center gap-2">
          <img src="/shiso-icon-64.png" alt="Shiso" class="h-8 w-8" />
          <h1 class="display-font text-3xl font-semibold">Shiso</h1>
        </div>
        <div class="flex flex-wrap gap-2">
          <Button @click="loadAll" :loading="loading" label="Refresh" icon="pi pi-refresh" severity="secondary" size="small" outlined />
          <Button @click="syncEnabledLogins" :loading="syncingAllLogins" :label="syncingAllLogins ? 'Syncing…' : 'Sync All'" icon="pi pi-sync" severity="success" size="small" />
        </div>
      </div>

      <Message v-if="statusMessage" :severity="statusError ? 'error' : 'success'" :closable="true" @close="statusMessage = ''">
        {{ statusMessage }}
      </Message>

      <!-- Summary -->
      <div class="grid gap-4 grid-cols-3">
        <Card>
          <template #content>
            <div class="text-xs uppercase tracking-widest text-surface-400">Assets</div>
            <div class="mt-1 text-2xl font-semibold text-green-400">{{ money(summary.asset_total) }}</div>
          </template>
        </Card>
        <Card>
          <template #content>
            <div class="text-xs uppercase tracking-widest text-surface-400">Liabilities</div>
            <div class="mt-1 text-2xl font-semibold text-amber-400">{{ money(summary.debt_total) }}</div>
          </template>
        </Card>
        <Card>
          <template #content>
            <div class="text-xs uppercase tracking-widest text-surface-400">Net Position</div>
            <div class="mt-1 text-2xl font-semibold" :class="(summary.net_balance || 0) >= 0 ? 'text-green-400' : 'text-red-400'">
              {{ signedMoney(summary.net_balance) }}
            </div>
          </template>
        </Card>
      </div>

      <!-- Problem Logins Alert -->
      <div v-if="problemLoginsDerived.length > 0" class="bg-red-950/50 border border-red-800 rounded-lg p-4">
        <div class="flex items-start gap-3">
          <i class="pi pi-exclamation-triangle text-red-400 text-xl mt-0.5" />
          <div class="flex-1">
            <h3 class="text-lg font-semibold text-red-300 mb-2">Attention Required</h3>
            <p class="text-sm text-red-200 mb-3">
              {{ problemLoginsDerived.length }} login(s) need authentication. Interactive login required to sync these accounts.
            </p>
            <div class="flex flex-wrap gap-2">
              <div v-for="login in problemLoginsDerived" :key="login.id" class="flex items-center gap-2 bg-surface-900 rounded px-3 py-2">
                <Tag 
                  :value="login.last_auth_status === 'needs_2fa' ? '2FA Required' : 'Login Failed'" 
                  :severity="login.last_auth_status === 'needs_2fa' ? 'warn' : 'danger'" 
                />
                <span class="font-medium">{{ login.institution || login.provider_key }}</span>
                <span class="text-xs text-surface-400">{{ login.username || login.label }}</span>
                <Button 
                  @click="startInteractiveAuthForLogin(login)" 
                  :loading="interactiveAuthLoading[login.id]"
                  :disabled="interactiveAuthLoading[login.id]"
                  label="Resolve 2FA" 
                  icon="pi pi-sign-in" 
                  severity="success" 
                  size="small"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Global search -->
      <div class="flex justify-end">
        <IconField>
          <InputIcon class="pi pi-search" />
          <InputText v-model="tableFilters['global'].value" placeholder="Search all accounts..." size="small" />
        </IconField>
      </div>

      <!-- Promo APR Tracker -->
      <PromosPanel :promos="promos" :loading="loading" @add="openPromoDialog()" @edit="openPromoDialog($event)" @delete="confirmDeletePromo($event)" />

      <!-- Rewards Tracker -->
      <RewardsPanel :rewards="rewards" :loading="loading" @add="openRewardsDialog()" @edit="openRewardsDialog($event)" />

      <!-- Bills: accounts with upcoming due dates -->
      <Section header="Bills" :count="billRows.length" persistKey="bills">
        <AccountTable
          :rows="billRows"
          v-model:filters="tableFilters"
          sortField="due_date"
          :sortOrder="1"
          emptyMessage="No bills with due dates found."
          showActions
          :canSyncRow="canSyncSnapshotRow"
          :canEditRow="canEditSnapshotRow"
          @sync="syncSnapshotRow"
          @edit="editSnapshotRow"
        >
          <Column field="due_date" header="Due" sortable>
            <template #body="{ data }">
              <span :class="isDueSoon(data.due_date) ? 'text-red-400 font-semibold' : ''">{{ data.due_date || '—' }}</span>
            </template>
          </Column>
          <Column field="minimum_payment" header="Min Payment" sortable>
            <template #body="{ data }">{{ data.minimum_payment ? money(data.minimum_payment) : '—' }}</template>
          </Column>
          <Column field="interest_rate" header="APR" sortable>
            <template #body="{ data }">
              <span v-if="data.interest_rate != null">{{ data.interest_rate }}%</span>
              <span v-else class="text-surface-500">—</span>
            </template>
          </Column>
        </AccountTable>
      </Section>

      <!-- Assets -->
      <Section header="Assets" :count="assetRows.length" persistKey="assets">
        <AccountTable
          :rows="assetRows"
          v-model:filters="tableFilters"
          balanceColor="text-green-400"
          emptyMessage="No asset accounts found."
          showActions
          :canSyncRow="canSyncSnapshotRow"
          :canEditRow="canEditSnapshotRow"
          @sync="syncSnapshotRow"
          @edit="editSnapshotRow"
        />
      </Section>

      <!-- Liabilities -->
      <Section header="Liabilities" :count="liabilityRows.length" persistKey="liabilities">
        <AccountTable
          :rows="liabilityRows"
          v-model:filters="tableFilters"
          emptyMessage="No liability accounts found."
          showActions
          :canSyncRow="canSyncSnapshotRow"
          :canEditRow="canEditSnapshotRow"
          @sync="syncSnapshotRow"
          @edit="editSnapshotRow"
        >
          <Column field="due_date" header="Due" sortable>
            <template #body="{ data }">{{ data.due_date || '—' }}</template>
          </Column>
          <Column field="minimum_payment" header="Min Payment" sortable>
            <template #body="{ data }">{{ data.minimum_payment ? money(data.minimum_payment) : '—' }}</template>
          </Column>
          <Column field="interest_rate" header="APR" sortable>
            <template #body="{ data }">
              <span v-if="data.interest_rate != null">{{ data.interest_rate }}%</span>
              <span v-else class="text-surface-500">—</span>
            </template>
          </Column>
        </AccountTable>
      </Section>

      <Section v-if="zeroBalanceRows.length" header="Zero Balance" :count="zeroBalanceRows.length" :collapsed="true" persistKey="zero-balance">
        <AccountTable
          :rows="zeroBalanceRows"
          v-model:filters="tableFilters"
          balanceColor="text-surface-300"
          emptyMessage="No zero-balance accounts found."
          showActions
          :canSyncRow="canSyncSnapshotRow"
          :canEditRow="canEditSnapshotRow"
          @sync="syncSnapshotRow"
          @edit="editSnapshotRow"
        />
      </Section>

<!-- Tools -->
      <ToolsPanel />

      <!-- Admin: Manage Logins -->
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

      <!-- Admin: Import Passwords -->
      <ImportPanel
        :previewData="importPreviewData"
        :importing="importing"
        @upload="handleFileUpload"
        @import="runImportFromSelection"
        @clear="clearImport"
      />
    </div>

    <PromoDialog
      v-model:visible="promoDialogVisible"
      v-model:form="promoForm"
      :edit="promoDialogEdit"
      :accounts="accountsList"
      :promoTypes="promoTypes"
      @save="savePromo"
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
      @save="saveRewardsProgram"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, reactive } from 'vue'
import { useToast } from 'primevue/usetoast'
import { useConfirm } from 'primevue/useconfirm'
import { FilterMatchMode } from '@primevue/core/api'
import {
  fetchDashboard,
  fetchLogins,
  createLogin,
  updateLogin,
  deleteLogin as apiDeleteLogin,
  fetchProviders,
  importPreview,
  importLogins,
  syncLogin as apiSyncLogin,
  syncLogins as apiSyncLogins,
  fetchPromos,
  createPromo,
  updatePromo as apiUpdatePromo,
  deletePromo as apiDeletePromo,
  fetchAccountsList,
  fetchAccountTypes,
  fetchProblemLogins,
  startInteractiveAuth,
  fetchInteractiveAuthStatus,
  respondInteractiveAuth,
  createRewardsProgram,
  updateRewardsProgram,
  fetchRewardsSummary,
} from './api.js'
import { money, signedMoney, relativeTime, typeSeverity, isDueSoon } from './helpers.js'

import Section from './components/Section.vue'
import AccountTable from './components/AccountTable.vue'
import InteractiveAuthDialog from './components/InteractiveAuthDialog.vue'
import LoginDialog from './components/LoginDialog.vue'
import PromoDialog from './components/PromoDialog.vue'
import PromosPanel from './components/PromosPanel.vue'
import RewardsDialog from './components/RewardsDialog.vue'
import RewardsPanel from './components/RewardsPanel.vue'
import LoginsPanel from './components/LoginsPanel.vue'
import ImportPanel from './components/ImportPanel.vue'
import ToolsPanel from './components/ToolsPanel.vue'

import Button from 'primevue/button'
import Card from 'primevue/card'
import Column from 'primevue/column'
import ConfirmDialog from 'primevue/confirmdialog'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import FileUpload from 'primevue/fileupload'
import InputText from 'primevue/inputtext'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import Textarea from 'primevue/textarea'
import Toast from 'primevue/toast'
import Toolbar from 'primevue/toolbar'

const toast = useToast()
const confirm = useConfirm()

const snapshots = ref([])
const summary = ref({})
const loading = ref(false)
const statusMessage = ref('')
const statusError = ref(false)
const tableFilters = ref({
  global: { value: null, matchMode: FilterMatchMode.CONTAINS },
})

const logins = ref([])
const loginsLoading = ref(false)
const syncingAllLogins = ref(false)
const providers = ref([])
const loginDialogVisible = ref(false)
const loginDialogEdit = ref(false)
const loginEditId = ref(null)
const loginForm = ref(defaultLoginForm())
const accountTypes = ref([])

// Problem logins (needs_2fa, login_failed)
const problemLogins = ref([])
const interactiveAuthLoading = reactive({})
const interactiveAuthDialogVisible = ref(false)
const interactiveAuthDialogLogin = ref(null)
const interactiveAuthSession = ref({
  login_id: null,
  provider_key: null,
  status: 'idle',
  message: 'No interactive auth session running.',
  prompt: null,
  updated_at: null,
})
const interactiveAuthResponse = ref('')
const interactiveAuthResponding = ref(false)
let interactiveAuthPollTimer = null

// Computed: derive from logins if not fetched separately
const problemLoginsDerived = computed(() => {
  if (problemLogins.value.length > 0) return problemLogins.value
  return logins.value.filter(l => l.last_auth_status === 'needs_2fa' || l.last_auth_status === 'login_failed')
})

const promos = ref([])
const accountsList = ref([])
const promoDialogVisible = ref(false)
const promoDialogEdit = ref(false)
const promoEditId = ref(null)
const promoForm = ref(defaultPromoForm())
const promoTypes = [
  { label: 'Purchase', value: 'purchase' },
  { label: 'Balance Transfer', value: 'balance_transfer' },
  { label: 'General', value: 'general' },
]

const rewardsDialogVisible = ref(false)
const rewardsDialogEdit = ref(false)
const rewardsEditId = ref(null)
const rewardsForm = ref(defaultRewardsForm())
const rewardsTypes = [
  { label: 'Points', value: 'points' },
  { label: 'Miles', value: 'miles' },
  { label: 'Cashback', value: 'cashback' },
  { label: 'Other', value: 'other' },
]
const rewards = ref([])

function defaultRewardsForm() {
  return { financial_account_id: null, program_name: '', program_type: 'points', unit_name: '', cents_per_unit: null }
}

function defaultPromoForm() {
  return { financial_account_id: null, promo_type: 'purchase', apr_rate: 0, regular_apr: null, start_date: '', end_date: '', original_amount: null, description: '' }
}

const importFile = ref(null)
const importPreviewData = ref(null)
const importing = ref(false)

function defaultLoginForm() {
  return { provider_key: '', institution: '', label: '', username: '', password: '', login_url: '', account_type: 'Credit Card', tool_key: 'financial_scraper', enabled: true, sort_order: 0 }
}

const ZERO_BALANCE_EPSILON = 0.005

function snapshotBalance(snapshot) {
  const balance = snapshot.current_balance ?? snapshot.statement_balance
  return typeof balance === 'number' ? balance : null
}

function isZeroBalanceSnapshot(snapshot) {
  const balance = snapshotBalance(snapshot)
  return balance !== null && Math.abs(balance) < ZERO_BALANCE_EPSILON
}

// Filtered views of snapshots
const billRows = computed(() =>
  snapshots.value
    .filter(s => !isZeroBalanceSnapshot(s) && (s.due_date || s.minimum_payment))
    .sort((a, b) => (a.due_date || '').localeCompare(b.due_date || ''))
)

const assetRows = computed(() =>
  snapshots.value.filter(s => s.balance_type === 'asset' && !isZeroBalanceSnapshot(s))
)

const liabilityRows = computed(() =>
  snapshots.value.filter(s => s.balance_type === 'liability' && !isZeroBalanceSnapshot(s))
)

const zeroBalanceRows = computed(() =>
  snapshots.value.filter(isZeroBalanceSnapshot)
)

const enabledLoginCount = computed(() => logins.value.filter(login => login.enabled).length)

const toolOptions = [{ label: 'Financial Scraper', value: 'financial_scraper' }]

function linkedLoginForSnapshot(snapshot) {
  if (!snapshot?.scraper_login_id) return null
  return logins.value.find(login => login.id === snapshot.scraper_login_id) || null
}

function canSyncSnapshotRow(snapshot) {
  const login = linkedLoginForSnapshot(snapshot)
  return !!(login && login.enabled && !['queued', 'running'].includes(login.last_sync_status))
}

function canEditSnapshotRow(snapshot) {
  return !!linkedLoginForSnapshot(snapshot)
}

function snapshotAccountFilter(snapshot) {
  const mask = String(snapshot?.account_mask || '').trim()
  if (mask) return mask
  const displayName = String(snapshot?.display_name || '').trim()
  if (displayName) return displayName
  const address = String(snapshot?.address || '').trim()
  return address || null
}

async function syncSnapshotRow(snapshot) {
  const login = linkedLoginForSnapshot(snapshot)
  if (!login) {
    toast.add({ severity: 'warn', summary: 'No Linked Login', detail: 'This account is not linked to a scraper login yet.', life: 4000 })
    return
  }
  const accountFilter = snapshotAccountFilter(snapshot)
  const accountLabel = snapshot.display_name || snapshot.account_mask || 'Account'
  await syncLoginRow(
    login,
    accountFilter ? { account_filter: accountFilter } : null,
    `${accountLabel} queued for sync`,
  )
}

function editSnapshotRow(snapshot) {
  const login = linkedLoginForSnapshot(snapshot)
  if (!login) {
    toast.add({ severity: 'warn', summary: 'No Linked Login', detail: 'This account is not linked to a scraper login yet.', life: 4000 })
    return
  }
openLoginDialog(login)
}

// Data loading — single function for mount + refresh
async function loadAll() {
  loading.value = true
  statusMessage.value = ''
  statusError.value = false
  try {
    const [dashboard, l, p, types, promosData, accounts, rewardsData] = await Promise.all([
      fetchDashboard(),
      fetchLogins(),
      fetchProviders(),
      fetchAccountTypes(),
      fetchPromos(true).catch(() => []),
      fetchAccountsList().catch(() => []),
      fetchRewardsSummary().catch(() => ({ programs: [] })),
    ])
    snapshots.value = dashboard.snapshots
    summary.value = dashboard.summary
    logins.value = l
    providers.value = p
    accountTypes.value = types.map(t => t.name)
    promos.value = promosData
    accountsList.value = accounts.map(a => ({ id: a.id, label: `${a.institution} — ${a.display_name || a.account_mask || 'Unnamed'}` }))
    rewards.value = rewardsData.programs || []
  } catch (err) {
    statusMessage.value = err.message
    statusError.value = true
  } finally {
    loading.value = false
  }
}

// Re-fetch just logins (after mutations like delete, import, sync)
async function loadLogins() {
  try {
    logins.value = await fetchLogins()
    try {
      problemLogins.value = await fetchProblemLogins()
    } catch {
      problemLogins.value = []
    }
  } catch (err) { toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 }) }
}

async function syncLoginRow(login, options = null, successDetail = null) {
  try {
    const result = await apiSyncLogin(login.id, options)
    if (result.status === 'already_queued') {
      toast.add({ severity: 'info', summary: 'Already Queued', detail: `${login.label} already has a sync in progress`, life: 3000 })
      return
    }
    const idx = logins.value.findIndex(l => l.id === login.id)
    if (idx >= 0) logins.value[idx].last_sync_status = 'queued'
    toast.add({ severity: 'info', summary: 'Queued', detail: successDetail || `${login.label} queued for sync`, life: 3000 })
  } catch (err) {
    toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 })
  }
}

async function syncEnabledLogins() {
  syncingAllLogins.value = true
  try {
    const result = await apiSyncLogins(null)
    toast.add({ severity: 'success', summary: 'Queued', detail: `${result.logins_queued} login(s) queued for sync`, life: 5000 })
    if (logins.value.length) await loadLogins()
  } catch (err) {
    toast.add({ severity: 'error', summary: 'Sync Failed', detail: err.message, life: 5000 })
  } finally {
    syncingAllLogins.value = false
  }
}

function stopInteractiveAuthPolling() {
  if (interactiveAuthPollTimer) {
    clearInterval(interactiveAuthPollTimer)
    interactiveAuthPollTimer = null
  }
}

function closeInteractiveAuthDialog() {
  interactiveAuthDialogVisible.value = false
  interactiveAuthResponse.value = ''
  stopInteractiveAuthPolling()
}

async function refreshInteractiveAuthSession() {
  const login = interactiveAuthDialogLogin.value
  if (!login) return

  try {
    interactiveAuthSession.value = await fetchInteractiveAuthStatus(login.id)
    if (['completed', 'failed', 'skipped', 'idle'].includes(interactiveAuthSession.value.status)) {
      stopInteractiveAuthPolling()
      await loadLogins()
    }
  } catch (err) {
    stopInteractiveAuthPolling()
    toast.add({ severity: 'error', summary: 'Auth Status Error', detail: err.message, life: 5000 })
  }
}

function openInteractiveAuthDialog(login, initialState = null) {
  interactiveAuthDialogLogin.value = login
  interactiveAuthDialogVisible.value = true
  interactiveAuthResponse.value = ''
  if (initialState) {
    interactiveAuthSession.value = initialState
  }
  stopInteractiveAuthPolling()
  interactiveAuthPollTimer = setInterval(() => {
    refreshInteractiveAuthSession()
  }, 2000)
}

async function startInteractiveAuthForLogin(login) {
  interactiveAuthLoading[login.id] = true
  try {
    const result = await startInteractiveAuth(login.id)
    openInteractiveAuthDialog(login, result)
    await refreshInteractiveAuthSession()
  } catch (err) {
    toast.add({ severity: 'error', summary: 'Failed to Start', detail: err.message, life: 5000 })
  } finally {
    interactiveAuthLoading[login.id] = false
  }
}

async function submitInteractiveAuthResponse(skip = false) {
  const login = interactiveAuthDialogLogin.value
  if (!login) return
  if (!skip && !interactiveAuthResponse.value.trim()) return

  interactiveAuthResponding.value = true
  try {
    interactiveAuthSession.value = await respondInteractiveAuth(login.id, {
      response: skip ? null : interactiveAuthResponse.value.trim(),
      skip,
    })
    interactiveAuthResponse.value = ''
    await refreshInteractiveAuthSession()
  } catch (err) {
    toast.add({ severity: 'error', summary: 'Failed to Send', detail: err.message, life: 5000 })
  } finally {
    interactiveAuthResponding.value = false
  }
}


function openLoginDialog(login = null) {
  if (login) {
    loginDialogEdit.value = true
    loginEditId.value = login.id
    loginForm.value = { provider_key: login.provider_key, institution: login.institution || '', label: login.label, username: login.username || '', password: '', login_url: login.login_url || '', account_type: login.account_type, tool_key: login.tool_key || 'financial_scraper', enabled: login.enabled, sort_order: login.sort_order }
  } else {
    loginDialogEdit.value = false
    loginEditId.value = null
    loginForm.value = defaultLoginForm()
  }
  loginDialogVisible.value = true
}

async function saveLogin() {
  const data = { ...loginForm.value, institution: loginForm.value.institution || null, login_url: loginForm.value.login_url || null, username: loginForm.value.username || null, password: loginForm.value.password || null, tool_key: loginForm.value.tool_key || 'financial_scraper' }
  try {
    if (loginDialogEdit.value) { await updateLogin(loginEditId.value, data); toast.add({ severity: 'success', summary: 'Updated', detail: data.label, life: 3000 }) }
    else { await createLogin(data); toast.add({ severity: 'success', summary: 'Created', detail: data.label, life: 3000 }) }
    loginDialogVisible.value = false
    await loadLogins()
  } catch (err) { toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 }) }
}

function confirmDeleteLogin(login) {
  confirm.require({
    message: `Delete "${login.label}"?`,
    header: 'Confirm Delete',
    icon: 'pi pi-trash',
    acceptClass: 'p-button-danger',
    accept: async () => {
      try { await apiDeleteLogin(login.id); toast.add({ severity: 'info', summary: 'Deleted', detail: login.label, life: 3000 }); await loadLogins() }
      catch (err) { toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 }) }
    },
  })
}

async function toggleEnabled(login) {
  const newVal = !login.enabled
  login.enabled = newVal
  try { await updateLogin(login.id, { ...login, enabled: newVal, login_url: login.login_url || null, password: null }) }
  catch (err) { login.enabled = !newVal; toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 }) }
}

// Import
async function handleFileUpload(event) {
  const file = event.files[0]
  if (!file) return
  importFile.value = file
  try { importPreviewData.value = await importPreview(file) }
  catch (err) { toast.add({ severity: 'error', summary: 'Parse Error', detail: err.message, life: 4000 }) }
}

function clearImport() { importPreviewData.value = null; importFile.value = null }

async function runImportFromSelection(selectedRows) {
  if (!importFile.value || !selectedRows.length) return
  importing.value = true
  try {
    const newIds = selectedRows.filter(r => !r.is_duplicate).map(r => r.row_id)
    const overwriteIds = selectedRows.filter(r => r.is_duplicate).map(r => r.row_id)
    const result = await importLogins(importFile.value, newIds, overwriteIds)
    const parts = []
    if (result.imported) parts.push(`${result.imported} imported`)
    if (result.updated) parts.push(`${result.updated} updated`)
    if (result.skipped) parts.push(`${result.skipped} skipped`)
    toast.add({ severity: 'success', summary: 'Import Complete', detail: parts.join(', '), life: 5000 })
    clearImport()
    await loadLogins()
  } catch (err) { toast.add({ severity: 'error', summary: 'Import Failed', detail: err.message, life: 4000 }) } finally { importing.value = false }
}

// Promos
function openPromoDialog(promo = null) {
  if (promo) {
    promoDialogEdit.value = true
    promoEditId.value = promo.id
    promoForm.value = {
      financial_account_id: promo.financial_account_id,
      promo_type: promo.promo_type,
      apr_rate: promo.apr_rate,
      regular_apr: promo.regular_apr,
      start_date: promo.start_date || '',
      end_date: promo.end_date,
      original_amount: promo.original_amount,
      description: promo.description || '',
    }
  } else {
    promoDialogEdit.value = false
    promoEditId.value = null
    promoForm.value = defaultPromoForm()
  }
  promoDialogVisible.value = true
}

async function savePromo() {
  const data = {
    ...promoForm.value,
    apr_rate: parseFloat(promoForm.value.apr_rate) || 0,
    regular_apr: promoForm.value.regular_apr ? parseFloat(promoForm.value.regular_apr) : null,
    original_amount: promoForm.value.original_amount ? parseFloat(promoForm.value.original_amount) : null,
    start_date: promoForm.value.start_date || null,
    description: promoForm.value.description || null,
  }
  try {
    if (promoDialogEdit.value) {
      await apiUpdatePromo(promoEditId.value, data)
      toast.add({ severity: 'success', summary: 'Updated', detail: 'Promo period updated', life: 3000 })
    } else {
      await createPromo(data)
      toast.add({ severity: 'success', summary: 'Created', detail: 'Promo period added', life: 3000 })
    }
    promoDialogVisible.value = false
    await loadAll()
  } catch (err) {
    toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 })
  }
}

function confirmDeletePromo(promo) {
  const label = promo.account_display_name || promo.account_institution || 'this promo'
  const typeLabel = ({ purchase: 'Purchase', balance_transfer: 'Balance Transfer', general: 'General' })[promo.promo_type] || promo.promo_type
  confirm.require({
    message: `Delete ${typeLabel} promo for "${label}"?`,
    header: 'Confirm Delete',
    icon: 'pi pi-trash',
    acceptClass: 'p-button-danger',
    accept: async () => {
      try {
        await apiDeletePromo(promo.id)
        toast.add({ severity: 'info', summary: 'Deleted', detail: 'Promo period removed', life: 3000 })
        await loadAll()
      } catch (err) {
        toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 })
      }
    },
  })
}



function openRewardsDialog(rewards = null) {
  if (rewards) {
    rewardsDialogEdit.value = true
    rewardsEditId.value = rewards.program_id
    rewardsForm.value = {
      financial_account_id: rewards.account_id,
      program_name: rewards.program_name,
      program_type: rewards.program_type || 'points',
      unit_name: rewards.unit_name || '',
      cents_per_unit: rewards.cents_per_unit,
    }
  } else {
    rewardsDialogEdit.value = false
    rewardsEditId.value = null
    rewardsForm.value = defaultRewardsForm()
  }
  rewardsDialogVisible.value = true
}

async function saveRewardsProgram() {
  const data = {
    ...rewardsForm.value,
    cents_per_unit: rewardsForm.value.cents_per_unit ? parseFloat(rewardsForm.value.cents_per_unit) : null,
  }
  try {
    if (rewardsDialogEdit.value) {
      await updateRewardsProgram(rewardsEditId.value, data)
      toast.add({ severity: 'success', summary: 'Updated', detail: 'Rewards program updated', life: 3000 })
    } else {
      await createRewardsProgram(data)
      toast.add({ severity: 'success', summary: 'Created', detail: 'Rewards program added', life: 3000 })
    }
    rewardsDialogVisible.value = false
    await loadAll()
  } catch (err) {
    toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 })
  }
}

onMounted(async () => {
  await loadAll()
})

onUnmounted(() => {
  stopInteractiveAuthPolling()
})
</script>
