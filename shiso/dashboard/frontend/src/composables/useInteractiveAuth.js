import { reactive, shallowRef } from 'vue'
import { useToast } from 'primevue/usetoast'
import {
  startInteractiveAuth,
  fetchInteractiveAuthStatus,
  respondInteractiveAuth,
} from '../api.js'

const interactiveAuthLoading = reactive({})
const interactiveAuthDialogVisible = shallowRef(false)
const interactiveAuthDialogLogin = shallowRef(null)
const interactiveAuthSession = shallowRef({
  login_id: null,
  provider_key: null,
  status: 'idle',
  message: 'No interactive auth session running.',
  prompt: null,
  updated_at: null,
})
const interactiveAuthResponse = shallowRef('')
const interactiveAuthResponding = shallowRef(false)
let interactiveAuthPollTimer = null
let reloadLoginsCallback = null

export function useInteractiveAuth({ reloadLogins }) {
  const toast = useToast()
  reloadLoginsCallback = reloadLogins

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
        if (reloadLoginsCallback) await reloadLoginsCallback()
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

  return {
    interactiveAuthLoading,
    interactiveAuthDialogVisible,
    interactiveAuthDialogLogin,
    interactiveAuthSession,
    interactiveAuthResponse,
    interactiveAuthResponding,
    stopInteractiveAuthPolling,
    closeInteractiveAuthDialog,
    startInteractiveAuthForLogin,
    submitInteractiveAuthResponse,
  }
}
