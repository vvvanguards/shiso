export function money(v) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(v || 0)
}

export function signedMoney(v) {
  const a = v || 0
  return a < 0 ? `-${money(Math.abs(a))}` : money(a)
}

export function relativeTime(v) {
  if (!v) return '—'
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? v : d.toLocaleString()
}

export function typeSeverity(v) {
  const key = (v || '').toLowerCase()
  if (key.includes('credit')) return 'info'
  if (key.includes('loan') || key.includes('line of credit')) return 'warn'
  if (key.includes('checking') || key.includes('saving') || key.includes('bank')) return 'success'
  if (key.includes('investment') || key.includes('brokerage') || key.includes('retirement')) return 'success'
  if (key.includes('utility')) return 'secondary'
  if (key.includes('insurance') || key.includes('property')) return 'contrast'
  return 'secondary'
}

export function isDueSoon(dateStr) {
  if (!dateStr) return false
  const diff = new Date(dateStr) - new Date()
  return diff >= 0 && diff < 7 * 24 * 60 * 60 * 1000
}
