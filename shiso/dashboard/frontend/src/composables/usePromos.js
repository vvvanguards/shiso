import { shallowRef } from 'vue'
import { useToast } from 'primevue/usetoast'
import { useConfirm } from 'primevue/useconfirm'
import {
  fetchPromos,
  createPromo,
  updatePromo as apiUpdatePromo,
  deletePromo as apiDeletePromo,
  fetchAccountsList,
} from '../api.js'

function defaultPromoForm() {
  return { financial_account_id: null, promo_type: 'purchase', apr_rate: 0, regular_apr: null, start_date: '', end_date: '', original_amount: null, description: '' }
}

const promos = shallowRef([])
const accountsList = shallowRef([])
const promoDialogVisible = shallowRef(false)
const promoDialogEdit = shallowRef(false)
const promoEditId = shallowRef(null)
const promoForm = shallowRef(defaultPromoForm())
const promoTypes = [
  { label: 'Purchase', value: 'purchase' },
  { label: 'Balance Transfer', value: 'balance_transfer' },
  { label: 'General', value: 'general' },
]

export function usePromos() {
  const toast = useToast()
  const confirm = useConfirm()

  async function loadPromos() {
    promos.value = await fetchPromos(true).catch(() => [])
    const accounts = await fetchAccountsList().catch(() => [])
    accountsList.value = accounts.map(a => ({ id: a.id, label: `${a.institution} — ${a.display_name || a.account_mask || 'Unnamed'}` }))
  }

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

  async function savePromo(onSuccess) {
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
      if (onSuccess) await onSuccess()
    } catch (err) {
      toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 })
    }
  }

  function confirmDeletePromo(promo, onSuccess) {
    const label = promo.display_name || promo.institution || 'this promo'
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
          if (onSuccess) await onSuccess()
        } catch (err) {
          toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 })
        }
      },
    })
  }

  return {
    promos,
    accountsList,
    promoDialogVisible,
    promoDialogEdit,
    promoEditId,
    promoForm,
    promoTypes,
    loadPromos,
    openPromoDialog,
    savePromo,
    confirmDeletePromo,
  }
}
