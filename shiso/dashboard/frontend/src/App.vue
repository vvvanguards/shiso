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
          <Button @click="refreshData" :loading="loading" label="Refresh" icon="pi pi-refresh" severity="secondary" size="small" outlined />
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

      <!-- Global search -->
      <div class="flex justify-end">
        <IconField>
          <InputIcon class="pi pi-search" />
          <InputText v-model="tableFilters['global'].value" placeholder="Search all accounts..." size="small" />
        </IconField>
      </div>

      <!-- Promo APR Tracker -->
      <Section v-if="promos.length || !loading" header="Promo APR Periods" :count="promos.length" persistKey="promos" class="promo-panel">
        <template #icons>
          <Button @click.stop="openPromoDialog()" icon="pi pi-plus" severity="success" size="small" text rounded v-tooltip.top="'Add promo period'" />
        </template>
        <DataTable :value="promos" stripedRows size="small" sortField="end_date" :sortOrder="1" v-if="promos.length">
          <Column header="Account">
            <template #body="{ data }">
              <div class="font-medium">{{ data.account_display_name || data.account_institution }}</div>
              <div v-if="data.account_mask" class="text-xs text-surface-400">••{{ data.account_mask }}</div>
            </template>
          </Column>
          <Column field="promo_type" header="Type" sortable>
            <template #body="{ data }">
              <Tag :value="promoTypeLabel(data.promo_type)" :severity="promoTypeSeverity(data.promo_type)" />
            </template>
          </Column>
          <Column field="apr_rate" header="Promo APR" sortable>
            <template #body="{ data }">
              <span class="font-semibold text-green-400">{{ data.apr_rate }}%</span>
            </template>
          </Column>
          <Column field="end_date" header="Expires" sortable>
            <template #body="{ data }">
              <span :class="promoUrgencyClass(data.days_remaining)">{{ data.end_date }}</span>
              <div class="text-xs" :class="promoUrgencyClass(data.days_remaining)">
                {{ data.days_remaining > 0 ? `${data.days_remaining} days left` : 'Expired' }}
              </div>
            </template>
          </Column>
          <Column field="original_amount" header="Amount">
            <template #body="{ data }">{{ data.original_amount ? money(data.original_amount) : '—' }}</template>
          </Column>
          <Column field="regular_apr" header="Regular APR">
            <template #body="{ data }">
              <span v-if="data.regular_apr != null" class="text-amber-400">{{ data.regular_apr }}%</span>
              <span v-else class="text-surface-500">—</span>
            </template>
          </Column>
          <Column header="" style="width: 6rem">
            <template #body="{ data }">
              <div class="flex gap-1">
                <Button @click="openPromoDialog(data)" icon="pi pi-pencil" severity="secondary" text rounded size="small" v-tooltip.top="'Edit promo'" />
                <Button @click="confirmDeletePromo(data)" icon="pi pi-trash" severity="danger" text rounded size="small" v-tooltip.top="'Delete promo'" />
              </div>
            </template>
          </Column>
          <template #empty>
            <div class="py-6 text-center text-surface-400">No promo periods tracked.</div>
          </template>
        </DataTable>
        <div v-else class="py-4 text-center text-surface-400">
          No promo periods tracked. <Button @click="openPromoDialog()" label="Add one" severity="secondary" size="small" text />
        </div>
      </Section>

      <!-- Bills: accounts with upcoming due dates -->
      <Section header="Bills" :count="billRows.length" persistKey="bills">
        <AccountTable :rows="billRows" v-model:filters="tableFilters" sortField="due_date" :sortOrder="1" emptyMessage="No bills with due dates found.">
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
        <AccountTable :rows="assetRows" v-model:filters="tableFilters" balanceColor="text-green-400" emptyMessage="No asset accounts found." />
      </Section>

      <!-- Liabilities -->
      <Section header="Liabilities" :count="liabilityRows.length" persistKey="liabilities">
        <AccountTable :rows="liabilityRows" v-model:filters="tableFilters" emptyMessage="No liability accounts found.">
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

      <!-- Tools -->
      <Section header="Tools" :collapsed="true" persistKey="tools" @toggle="(e) => { if (!e.value && !tools.value.length) loadLogins() }">
        <div v-if="!tools.length" class="py-4 text-center text-surface-400">No tools registered.</div>
        <div v-else class="space-y-4">
          <DataTable :value="tools" stripedRows size="small">
            <Column field="display_name" header="Tool" sortable>
              <template #body="{ data }">
                <div class="font-medium">{{ data.display_name }}</div>
                <div class="text-xs text-surface-400">{{ data.tool_key }}</div>
              </template>
            </Column>
            <Column field="description" header="Description" />
            <Column header="" style="width: 6rem">
              <template #body="{ data }">
                <Button @click="loadToolRuns(data.tool_key)" icon="pi pi-list" severity="secondary" text rounded size="small" v-tooltip.top="'View runs'" />
              </template>
            </Column>
          </DataTable>

          <div v-if="selectedToolKey && toolRuns.length" class="mt-4">
            <h3 class="text-sm uppercase tracking-widest text-surface-400 mb-2">Recent Runs: {{ selectedToolKey }}</h3>
            <DataTable :value="toolRuns" stripedRows size="small" :rows="10" :paginator="toolRuns.length > 10">
              <Column field="created_at" header="Date" sortable>
                <template #body="{ data }">{{ relativeTime(data.created_at) }}</template>
              </Column>
              <Column field="provider_key" header="Provider" sortable />
              <Column field="items_count" header="Items" sortable />
              <Column header="Output">
                <template #body="{ data }">
                  <span class="text-xs text-surface-400 truncate block max-w-[300px]">{{ JSON.stringify(data.output_json).substring(0, 100) }}...</span>
                </template>
              </Column>
            </DataTable>
          </div>
        </div>
      </Section>

      <!-- Admin: Manage Logins -->
      <Section header="Manage Logins" :collapsed="true" persistKey="logins" @toggle="onLoginsToggle" @ready="onLoginsReady">
        <template #icons>
          <Button @click.stop="openLoginDialog()" icon="pi pi-plus" severity="success" size="small" text rounded />
          <Button
            @click.stop="syncEnabledLogins"
            :loading="syncingAllLogins"
            :disabled="!enabledLoginCount"
            icon="pi pi-sync"
            severity="secondary"
            size="small"
            text
            rounded
            v-tooltip.top="'Sync all enabled'"
          />
        </template>

        <DataTable :value="logins" stripedRows size="small" :loading="loginsLoading" sortField="provider_key" :sortOrder="1" :rowClass="(data) => !data.enabled ? 'opacity-50' : ''">
          <Column header="Provider" sortField="provider_key" sortable>
            <template #body="{ data }">
              <div class="font-medium">{{ data.institution || data.provider_key }}</div>
              <div class="text-xs text-surface-400">{{ data.label }}</div>
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
                <span class="text-sm text-surface-300">{{ syncTimestamp(data) }}</span>
              </div>
            </template>
          </Column>
          <Column header="" style="width: 8rem">
            <template #body="{ data }">
              <div class="flex gap-1">
                <Button @click="syncLoginRow(data)" icon="pi pi-sync" severity="success" text rounded size="small" :disabled="!data.enabled || data.last_sync_status === 'queued'" v-tooltip.top="'Sync now'" />
                <Button @click="openLoginDialog(data)" icon="pi pi-pencil" severity="secondary" text rounded size="small" v-tooltip.top="'Edit'" />
                <Button @click="toggleEnabled(data)" :icon="data.enabled ? 'pi pi-pause' : 'pi pi-play'" severity="info" text rounded size="small" v-tooltip.top="data.enabled ? 'Pause' : 'Resume'" />
                <Button @click="confirmDeleteLogin(data)" icon="pi pi-trash" severity="danger" text rounded size="small" v-tooltip.top="'Delete'" />
              </div>
            </template>
          </Column>
          <template #empty>
            <div class="py-6 text-center text-surface-400">No logins configured.</div>
          </template>
        </DataTable>
      </Section>

      <!-- Admin: Import Passwords -->
      <Section header="Import Passwords" :collapsed="true" persistKey="import" class="mb-12">
        <div v-if="!importPreviewData" class="flex items-center gap-4">
          <FileUpload mode="basic" accept=".csv" :auto="true" chooseLabel="Choose CSV File" customUpload @uploader="handleFileUpload" />
          <span class="text-sm text-surface-400">Export from chrome://password-manager/settings</span>
        </div>

        <div v-else>
          <Toolbar class="mb-4">
            <template #start>
              <div class="flex items-center gap-3 text-sm">
                <Tag :value="`${importPreviewData.matched.length} matched`" severity="success" />
                <Tag :value="`${importPreviewData.unmatched.length} unmatched`" severity="secondary" />
                <Tag :value="`${importSelectedRows.length} selected`" severity="info" />
              </div>
            </template>
            <template #end>
              <div class="flex gap-2">
                <Button @click="showUnmatched = !showUnmatched" :label="showUnmatched ? 'Hide Unmatched' : 'Show Unmatched'" severity="secondary" size="small" outlined />
                <Button @click="clearImport" label="Clear" severity="secondary" size="small" outlined />
                <Button @click="runImport" :loading="importing" :label="`Import ${importSelectedRows.length} Selected`" :disabled="!importSelectedRows.length" severity="success" size="small" />
              </div>
            </template>
          </Toolbar>

          <DataTable :value="importPreviewData.matched" v-model:selection="importSelectedRows" dataKey="row_id" scrollable scrollHeight="400px" size="small">
            <Column selectionMode="multiple" headerStyle="width: 3rem" />
            <Column header="Provider">
              <template #body="{ data }">
                <div class="font-medium">{{ data.provider_label }}</div>
                <div class="text-xs text-surface-400">{{ data.provider_key }}</div>
              </template>
            </Column>
            <Column field="account_type" header="Type">
              <template #body="{ data }">
                <Tag :value="data.account_type" severity="secondary" />
              </template>
            </Column>
            <Column field="username" header="Username" />
            <Column header="Password">
              <template #body="{ data }">{{ data.has_password ? '••••••••' : '—' }}</template>
            </Column>
          </DataTable>

          <div v-if="showUnmatched" class="mt-4">
            <h3 class="text-sm uppercase tracking-widest text-surface-400 mb-2">Unmatched ({{ importPreviewData.unmatched.length }})</h3>
            <DataTable :value="importPreviewData.unmatched" scrollable scrollHeight="300px" size="small">
              <Column field="name" header="Site" />
              <Column field="username" header="Username">
                <template #body="{ data }">{{ data.username || '—' }}</template>
              </Column>
              <Column field="url" header="URL">
                <template #body="{ data }">
                  <span class="text-xs text-surface-400 truncate block max-w-[300px]">{{ data.url }}</span>
                </template>
              </Column>
            </DataTable>
          </div>
        </div>
      </Section>
    </div>

    <!-- Promo Dialog -->
    <Dialog v-model:visible="promoDialogVisible" :header="promoDialogEdit ? 'Edit Promo Period' : 'Add Promo Period'" modal :style="{ width: '480px' }">
      <div class="flex flex-col gap-4 pt-2">
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium">Account</label>
          <Select v-model="promoForm.financial_account_id" :options="accountsList" optionLabel="label" optionValue="id" placeholder="Select account" fluid />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium">Promo Type</label>
          <Select v-model="promoForm.promo_type" :options="promoTypes" optionLabel="label" optionValue="value" fluid />
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div class="flex flex-col gap-1">
            <label class="text-sm font-medium">Promo APR %</label>
            <InputText v-model="promoForm.apr_rate" type="number" step="0.01" fluid />
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-sm font-medium">Regular APR %</label>
            <InputText v-model="promoForm.regular_apr" type="number" step="0.01" placeholder="Optional" fluid />
          </div>
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div class="flex flex-col gap-1">
            <label class="text-sm font-medium">Start Date</label>
            <InputText v-model="promoForm.start_date" type="date" fluid />
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-sm font-medium">End Date</label>
            <InputText v-model="promoForm.end_date" type="date" fluid />
          </div>
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium">Original Amount</label>
          <InputText v-model="promoForm.original_amount" type="number" step="0.01" placeholder="Optional" fluid />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium">Description</label>
          <InputText v-model="promoForm.description" placeholder="Optional note" fluid />
        </div>
      </div>
      <template #footer>
        <Button @click="promoDialogVisible = false" label="Cancel" severity="secondary" text />
        <Button @click="savePromo" :label="promoDialogEdit ? 'Update' : 'Create'" severity="success" />
      </template>
    </Dialog>

    <!-- Login Dialog -->
    <Dialog v-model:visible="loginDialogVisible" :header="loginDialogEdit ? 'Edit Login' : 'Add Login'" modal :style="{ width: '480px' }">
      <div class="flex flex-col gap-4 pt-2">
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium">Provider Key</label>
          <AutoComplete v-model="loginForm.provider_key" :suggestions="filteredProviders" @complete="searchProviders" placeholder="e.g. amex" fluid />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium">Institution</label>
          <InputText v-model="loginForm.institution" placeholder="e.g. Bank of America" fluid />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium">Label</label>
          <InputText v-model="loginForm.label" placeholder="Display label" fluid />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium">Account Type</label>
          <Select v-model="loginForm.account_type" :options="accountTypes" fluid />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium">Tool</label>
          <Select v-model="loginForm.tool_key" :options="toolOptions" optionLabel="label" optionValue="value" fluid />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium">Username</label>
          <InputText v-model="loginForm.username" placeholder="Username" fluid />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium">Password</label>
          <Password v-model="loginForm.password" :placeholder="loginDialogEdit ? '(unchanged)' : 'Password'" toggleMask :feedback="false" fluid />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium">Login URL</label>
          <InputText v-model="loginForm.login_url" placeholder="https://..." fluid />
        </div>
        <div class="flex items-center gap-2">
          <ToggleSwitch v-model="loginForm.enabled" />
          <label class="text-sm">Enabled</label>
        </div>
      </div>
      <template #footer>
        <Button @click="loginDialogVisible = false" label="Cancel" severity="secondary" text />
        <Button @click="saveLogin" :label="loginDialogEdit ? 'Update' : 'Create'" severity="success" />
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
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
  fetchTools,
  fetchToolRuns,
} from './api.js'
import { money, signedMoney, relativeTime, typeSeverity, isDueSoon } from './helpers.js'

import Section from './components/Section.vue'
import AccountTable from './components/AccountTable.vue'

import AutoComplete from 'primevue/autocomplete'
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
import Password from 'primevue/password'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import Toast from 'primevue/toast'
import ToggleSwitch from 'primevue/toggleswitch'
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
const filteredProviders = ref([])
const loginDialogVisible = ref(false)
const loginDialogEdit = ref(false)
const loginEditId = ref(null)
const loginForm = ref(defaultLoginForm())
const accountTypes = ref([])

const promos = ref([])
const accountsList = ref([])
const tools = ref([])
const toolRuns = ref([])
const selectedToolKey = ref(null)
const promoDialogVisible = ref(false)
const promoDialogEdit = ref(false)
const promoEditId = ref(null)
const promoForm = ref(defaultPromoForm())
const promoTypes = [
  { label: 'Purchase', value: 'purchase' },
  { label: 'Balance Transfer', value: 'balance_transfer' },
  { label: 'General', value: 'general' },
]

function defaultPromoForm() {
  return { financial_account_id: null, promo_type: 'purchase', apr_rate: 0, regular_apr: null, start_date: '', end_date: '', original_amount: null, description: '' }
}

const importFile = ref(null)
const importPreviewData = ref(null)
const importSelectedRows = ref([])
const importing = ref(false)
const showUnmatched = ref(false)

function defaultLoginForm() {
  return { provider_key: '', institution: '', label: '', username: '', password: '', login_url: '', account_type: 'Credit Card', tool_key: 'financial_scraper', enabled: true, sort_order: 0 }
}

// Filtered views of snapshots
const billRows = computed(() =>
  snapshots.value.filter(s => s.due_date || s.minimum_payment).sort((a, b) => (a.due_date || '').localeCompare(b.due_date || ''))
)

const assetRows = computed(() =>
  snapshots.value.filter(s => s.balance_type === 'asset')
)

const liabilityRows = computed(() =>
  snapshots.value.filter(s => s.balance_type === 'liability')
)

const enabledLoginCount = computed(() => logins.value.filter(login => login.enabled).length)

const toolOptions = computed(() =>
  tools.value.map(t => ({ label: t.display_name, value: t.tool_key }))
)

async function loadToolRuns(toolKey) {
  selectedToolKey.value = toolKey
  try {
    toolRuns.value = await fetchToolRuns(toolKey)
  } catch (err) {
    toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 })
  }
}

// Data loading
async function loadDashboard() {
  loading.value = true
  try {
    const data = await fetchDashboard()
    snapshots.value = data.snapshots
    summary.value = data.summary
    // Non-critical: don't block dashboard if these fail
    Promise.all([fetchPromos(true), fetchAccountsList()]).then(([promosData, accounts]) => {
      promos.value = promosData
      accountsList.value = accounts.map(a => ({ id: a.id, label: `${a.institution} — ${a.display_name || a.account_mask || 'Unnamed'}` }))
    }).catch(() => {})
  } finally {
    loading.value = false
  }
}

async function refreshData() {
  statusMessage.value = ''
  statusError.value = false
  try { await loadDashboard() } catch (err) { statusMessage.value = err.message; statusError.value = true }
}

// Logins
async function loadLogins() {
  loginsLoading.value = true
  try {
    const [l, p, types, t] = await Promise.all([fetchLogins(), fetchProviders(), fetchAccountTypes(), fetchTools()])
    logins.value = l
    providers.value = p
    accountTypes.value = types.map(t => t.name)
    tools.value = t
  } catch (err) { toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 }) } finally { loginsLoading.value = false }
}

async function syncLoginRow(login) {
  try {
    await apiSyncLogin(login.id)
    const idx = logins.value.findIndex(l => l.id === login.id)
    if (idx >= 0) logins.value[idx].last_sync_status = 'queued'
    toast.add({ severity: 'info', summary: 'Queued', detail: `${login.label} queued for sync`, life: 3000 })
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

function onLoginsToggle(e) { if (!e.value && !logins.value.length) loadLogins() }
function onLoginsReady(collapsed) { if (!collapsed && !logins.value.length) loadLogins() }

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

function searchProviders(event) { filteredProviders.value = providers.value.filter(p => p.toLowerCase().includes(event.query.toLowerCase())) }

// Import
async function handleFileUpload(event) {
  const file = event.files[0]
  if (!file) return
  importFile.value = file
  try { importPreviewData.value = await importPreview(file); importSelectedRows.value = [...importPreviewData.value.matched] }
  catch (err) { toast.add({ severity: 'error', summary: 'Parse Error', detail: err.message, life: 4000 }) }
}

function clearImport() { importPreviewData.value = null; importFile.value = null; importSelectedRows.value = [] }

async function runImport() {
  if (!importFile.value || !importSelectedRows.value.length) return
  importing.value = true
  try {
    const selectedIds = importSelectedRows.value.map(r => r.row_id)
    const result = await importLogins(importFile.value, selectedIds)
    toast.add({ severity: 'success', summary: 'Import Complete', detail: `Imported ${result.imported}, skipped ${result.skipped} dupes`, life: 5000 })
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
    await loadDashboard()
  } catch (err) {
    toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 })
  }
}

function confirmDeletePromo(promo) {
  const label = promo.account_display_name || promo.account_institution || 'this promo'
  confirm.require({
    message: `Delete ${promoTypeLabel(promo.promo_type)} promo for "${label}"?`,
    header: 'Confirm Delete',
    icon: 'pi pi-trash',
    acceptClass: 'p-button-danger',
    accept: async () => {
      try {
        await apiDeletePromo(promo.id)
        toast.add({ severity: 'info', summary: 'Deleted', detail: 'Promo period removed', life: 3000 })
        await loadDashboard()
      } catch (err) {
        toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 })
      }
    },
  })
}

function promoTypeLabel(type) {
  return ({ purchase: 'Purchase', balance_transfer: 'Balance Transfer', general: 'General' })[type] || type
}
function promoTypeSeverity(type) {
  return ({ purchase: 'info', balance_transfer: 'warn', general: 'secondary' })[type] || 'secondary'
}
function promoUrgencyClass(daysRemaining) {
  if (daysRemaining <= 0) return 'text-red-400 font-semibold'
  if (daysRemaining <= 30) return 'text-red-400 font-semibold'
  if (daysRemaining <= 90) return 'text-amber-400'
  return ''
}

// Helpers (shared helpers in helpers.js, these are App-specific)
function syncIcon(login) {
  if (login.last_auth_status === 'needs_2fa') return 'pi pi-exclamation-triangle text-amber-400'
  if (login.last_auth_status === 'login_failed') return 'pi pi-times-circle text-red-400'
  const s = login.last_sync_status
  if (!s) return 'pi pi-minus-circle text-surface-500'
  if (s === 'queued' || s === 'running') return 'pi pi-spin pi-spinner text-blue-400'
  if (s === 'succeeded') return 'pi pi-check-circle text-green-400'
  return 'pi pi-times-circle text-red-400'
}
function syncTimestamp(login) {
  const ts = login.last_sync_finished_at || login.last_sync_started_at
  if (!ts) return 'Never'
  return relativeTime(ts)
}

onMounted(async () => {
  try { await loadDashboard() } catch (err) { statusMessage.value = err.message; statusError.value = true }
})
</script>
