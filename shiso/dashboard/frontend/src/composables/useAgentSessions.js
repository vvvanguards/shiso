import { ref, shallowRef } from 'vue'
import { useToast } from 'primevue/usetoast'
import {
  fetchAgentSessions,
  fetchAgentSession,
  respondAgentSession,
} from '../api.js'

const activeSessions = ref([])
const agentDialogVisible = shallowRef(false)
const agentDialogSession = shallowRef(null)
const agentResponse = shallowRef('')
const agentResponding = shallowRef(false)
let pollTimer = null

export function useAgentSessions() {
  const toast = useToast()

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function loadActiveSessions() {
    try {
      activeSessions.value = await fetchAgentSessions()
    } catch {
      // Silently fail — sessions are optional
    }
  }

  async function refreshDialogSession() {
    const session = agentDialogSession.value
    if (!session) return

    try {
      const updated = await fetchAgentSession(session.run_id)
      agentDialogSession.value = updated

      // Check if any session needs attention
      if (['completed', 'failed'].includes(updated.status)) {
        stopPolling()
        await loadActiveSessions()
      }
    } catch (err) {
      stopPolling()
      toast.add({ severity: 'error', summary: 'Session Error', detail: err.message, life: 5000 })
    }
  }

  function openAgentDialog(session) {
    agentDialogSession.value = session
    agentDialogVisible.value = true
    agentResponse.value = ''
    stopPolling()
    pollTimer = setInterval(refreshDialogSession, 2000)
  }

  function closeAgentDialog() {
    agentDialogVisible.value = false
    agentResponse.value = ''
    stopPolling()
  }

  async function submitAgentResponse(skip = false) {
    const session = agentDialogSession.value
    if (!session) return
    if (!skip && !agentResponse.value.trim()) return

    agentResponding.value = true
    try {
      agentDialogSession.value = await respondAgentSession(session.run_id, {
        response: skip ? null : agentResponse.value.trim(),
        skip,
      })
      agentResponse.value = ''
      await refreshDialogSession()
    } catch (err) {
      toast.add({ severity: 'error', summary: 'Failed to Send', detail: err.message, life: 5000 })
    } finally {
      agentResponding.value = false
    }
  }

  return {
    activeSessions,
    agentDialogVisible,
    agentDialogSession,
    agentResponse,
    agentResponding,
    loadActiveSessions,
    openAgentDialog,
    closeAgentDialog,
    submitAgentResponse,
    stopPolling,
  }
}
