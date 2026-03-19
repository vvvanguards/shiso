import { computed, ref, shallowRef, provide, inject } from 'vue'
import { useToast } from 'primevue/usetoast'
import { FilterMatchMode } from '@primevue/core/api'
import { fetchDashboard } from '../api.js'

const ACTIVE_SECTION_KEY = 'activeSection'

export function provideActiveSection(initial = 'bills') {
  const activeSection = ref(initial)
  provide(ACTIVE_SECTION_KEY, activeSection)
  return activeSection
}

export function useActiveSection() {
  return inject(ACTIVE_SECTION_KEY)
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

const snapshots = shallowRef([])
const summary = shallowRef({})
const loading = shallowRef(false)
const statusMessage = shallowRef('')
const statusError = shallowRef(false)
const tableFilters = shallowRef({
  global: { value: null, matchMode: FilterMatchMode.CONTAINS },
})

const billRows = computed(() =>
  (snapshots.value || [])
    .filter(s => !isZeroBalanceSnapshot(s) && (s.due_date || s.minimum_payment))
    .sort((a, b) => (a.due_date || '').localeCompare(b.due_date || ''))
)

const assetRows = computed(() =>
  (snapshots.value || []).filter(s => s.balance_type === 'asset' && !isZeroBalanceSnapshot(s))
)

const liabilityRows = computed(() =>
  (snapshots.value || []).filter(s => s.balance_type === 'liability' && !isZeroBalanceSnapshot(s))
)

const zeroBalanceRows = computed(() =>
  (snapshots.value || []).filter(isZeroBalanceSnapshot)
)

export function useDashboard() {
  const toast = useToast()

  function snapshotAccountFilter(snapshot) {
    const mask = String(snapshot?.account_mask || '').trim()
    if (mask) return mask
    const displayName = String(snapshot?.display_name || '').trim()
    if (displayName) return displayName
    const address = String(snapshot?.address || '').trim()
    return address || null
  }

  function linkedLoginForSnapshot(snapshot, logins) {
    if (!snapshot?.scraper_login_id) return null
    const loginArray = logins?.value || []
    return loginArray.find(login => login.id === snapshot.scraper_login_id) || null
  }

  function canSyncSnapshotRow(snapshot, logins) {
    const login = linkedLoginForSnapshot(snapshot, logins)
    return !!(login && login.enabled && !['queued', 'running'].includes(login.last_sync_status))
  }

  function canEditSnapshotRow(snapshot, logins) {
    return !!linkedLoginForSnapshot(snapshot, logins)
  }

  async function syncSnapshotRow(snapshot, logins, syncLoginRow) {
    const login = linkedLoginForSnapshot(snapshot, logins)
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

  function editSnapshotRow(snapshot, logins, openLoginDialog) {
    const login = linkedLoginForSnapshot(snapshot, logins)
    if (!login) {
      toast.add({ severity: 'warn', summary: 'No Linked Login', detail: 'This account is not linked to a scraper login yet.', life: 4000 })
      return
    }
    openLoginDialog(login)
  }

  async function loadDashboard() {
    const dashboard = await fetchDashboard()
    snapshots.value = dashboard.snapshots
    summary.value = dashboard.summary
  }

  return {
    snapshots,
    summary,
    loading,
    statusMessage,
    statusError,
    tableFilters,
    billRows,
    assetRows,
    liabilityRows,
    zeroBalanceRows,
    snapshotBalance,
    isZeroBalanceSnapshot,
    snapshotAccountFilter,
    linkedLoginForSnapshot,
    canSyncSnapshotRow,
    canEditSnapshotRow,
    syncSnapshotRow,
    editSnapshotRow,
    loadDashboard,
  }
}
