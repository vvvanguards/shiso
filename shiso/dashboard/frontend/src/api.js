const API_BASE = '/api'

export async function fetchDashboard() {
  const response = await fetch(`${API_BASE}/accounts`)
  if (!response.ok) throw new Error('Failed to fetch dashboard data')
  return response.json()
}

export async function fetchLogins() {
  const response = await fetch(`${API_BASE}/logins`)
  if (!response.ok) throw new Error('Failed to fetch logins')
  return response.json()
}

export async function createLogin(data) {
  const response = await fetch(`${API_BASE}/logins`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to create login')
  }
  return response.json()
}

export async function updateLogin(id, data) {
  const response = await fetch(`${API_BASE}/logins/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to update login')
  }
  return response.json()
}

export async function deleteLogin(id) {
  const response = await fetch(`${API_BASE}/logins/${id}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to delete login')
  }
  return response.json()
}

export async function syncLogin(id) {
  const response = await fetch(`${API_BASE}/logins/${id}/sync`, {
    method: 'POST',
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to sync login')
  }
  return response.json()
}

export async function syncLogins(loginIds = null) {
  const response = await fetch(`${API_BASE}/logins/sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ login_ids: loginIds }),
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to sync logins')
  }
  return response.json()
}

export async function fetchProviders() {
  const response = await fetch(`${API_BASE}/logins/providers`)
  if (!response.ok) throw new Error('Failed to fetch providers')
  return response.json()
}

export async function importPreview(file) {
  const form = new FormData()
  form.append('file', file)
  const response = await fetch(`${API_BASE}/logins/import/preview`, {
    method: 'POST',
    body: form,
  })
  if (!response.ok) throw new Error('Failed to parse CSV')
  return response.json()
}

export async function fetchAprSummary() {
  const response = await fetch(`${API_BASE}/statements/apr-summary`)
  if (!response.ok) throw new Error('Failed to fetch APR summary')
  return response.json()
}

export async function fetchPromos(activeOnly = false) {
  const response = await fetch(`${API_BASE}/promos${activeOnly ? '?active_only=true' : ''}`)
  if (!response.ok) throw new Error('Failed to fetch promos')
  return response.json()
}

export async function createPromo(data) {
  const response = await fetch(`${API_BASE}/promos`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to create promo')
  }
  return response.json()
}

export async function updatePromo(id, data) {
  const response = await fetch(`${API_BASE}/promos/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to update promo')
  }
  return response.json()
}

export async function deletePromo(id) {
  const response = await fetch(`${API_BASE}/promos/${id}`, { method: 'DELETE' })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to delete promo')
  }
  return response.json()
}

export async function fetchAccountTypes() {
  const response = await fetch(`${API_BASE}/account-types`)
  if (!response.ok) throw new Error('Failed to fetch account types')
  return response.json()
}

export async function fetchAccountsList() {
  const response = await fetch(`${API_BASE}/accounts/list`)
  if (!response.ok) throw new Error('Failed to fetch accounts')
  return response.json()
}

export async function importLogins(file, selectedRowIds) {
  const form = new FormData()
  form.append('file', file)
  form.append('selected', selectedRowIds.join(','))
  // Re-upload as multipart — the backend re-parses to get passwords
  const response = await fetch(`${API_BASE}/logins/import?selected=${selectedRowIds.join(',')}`, {
    method: 'POST',
    body: form,
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || 'Import failed')
  }
  return response.json()
}
