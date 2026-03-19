import { computed, shallowRef } from 'vue'
import { useToast } from 'primevue/usetoast'
import { useConfirm } from 'primevue/useconfirm'
import {
  fetchLogins,
  createLogin,
  updateLogin,
  deleteLogin as apiDeleteLogin,
  fetchProviders,
  fetchAccountTypes,
  fetchProblemLogins,
  syncLogin as apiSyncLogin,
  syncLogins as apiSyncLogins,
} from '../api.js'

function defaultLoginForm() {
  return { provider_key: '', institution: '', label: '', username: '', password: '', login_url: '', account_type: 'Credit Card', tool_key: 'financial_scraper', enabled: true, sort_order: 0 }
}

const logins = shallowRef([])
const loginsLoading = shallowRef(false)
const syncingAllLogins = shallowRef(false)
const providers = shallowRef([])
const accountTypes = shallowRef([])
const loginDialogVisible = shallowRef(false)
const loginDialogEdit = shallowRef(false)
const loginEditId = shallowRef(null)
const loginForm = shallowRef(defaultLoginForm())
const problemLogins = shallowRef([])
const toolOptions = [{ label: 'Financial Scraper', value: 'financial_scraper' }]

const problemLoginsDerived = computed(() => {
  const probs = problemLogins.value || []
  if (probs.length > 0) return probs
  const loginList = logins.value || []
  return loginList.filter(l => l.last_auth_status === 'needs_2fa' || l.last_auth_status === 'login_failed')
})

const enabledLoginCount = computed(() => {
  const loginList = logins.value || []
  return loginList.filter(login => login.enabled).length
})

export function useLogins() {
  const toast = useToast()
  const confirm = useConfirm()

  async function loadLogins() {
    try {
      logins.value = await fetchLogins()
      try {
        problemLogins.value = await fetchProblemLogins()
      } catch {
        problemLogins.value = []
      }
    } catch (err) {
      toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 })
    }
  }

  async function loadProviders() {
    providers.value = await fetchProviders()
    const types = await fetchAccountTypes()
    accountTypes.value = types.map(t => t.name)
  }

  async function syncLoginRow(login, options = null, successDetail = null) {
    try {
      const result = await apiSyncLogin(login.id, options)
      if (result.status === 'already_queued') {
        toast.add({ severity: 'info', summary: 'Already Queued', detail: `${login.label} already has a sync in progress`, life: 3000 })
        return
      }
      const idx = logins.value.findIndex(l => l.id === login.id)
      if (idx >= 0) {
        logins.value = logins.value.map((l, i) => i === idx ? { ...l, last_sync_status: 'queued' } : l)
      }
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
      if (loginDialogEdit.value) {
        await updateLogin(loginEditId.value, data)
        toast.add({ severity: 'success', summary: 'Updated', detail: data.label, life: 3000 })
      } else {
        await createLogin(data)
        toast.add({ severity: 'success', summary: 'Created', detail: data.label, life: 3000 })
      }
      loginDialogVisible.value = false
      await loadLogins()
    } catch (err) {
      toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 })
    }
  }

  function confirmDeleteLogin(login) {
    confirm.require({
      message: `Delete "${login.label}"?`,
      header: 'Confirm Delete',
      icon: 'pi pi-trash',
      acceptClass: 'p-button-danger',
      accept: async () => {
        try {
          await apiDeleteLogin(login.id)
          toast.add({ severity: 'info', summary: 'Deleted', detail: login.label, life: 3000 })
          await loadLogins()
        } catch (err) {
          toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 })
        }
      },
    })
  }

  async function toggleEnabled(login) {
    const newVal = !login.enabled
    login.enabled = newVal
    try {
      await updateLogin(login.id, { ...login, enabled: newVal, login_url: login.login_url || null, password: null })
    } catch (err) {
      login.enabled = !newVal
      toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 })
    }
  }

  return {
    logins,
    loginsLoading,
    syncingAllLogins,
    providers,
    accountTypes,
    loginDialogVisible,
    loginDialogEdit,
    loginEditId,
    loginForm,
    problemLogins,
    problemLoginsDerived,
    enabledLoginCount,
    toolOptions,
    loadLogins,
    loadProviders,
    syncLoginRow,
    syncEnabledLogins,
    openLoginDialog,
    saveLogin,
    confirmDeleteLogin,
    toggleEnabled,
  }
}
