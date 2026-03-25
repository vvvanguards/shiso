import { shallowRef } from 'vue'
import { useToast } from 'primevue/usetoast'
import {
  createRewardsProgram,
  updateRewardsProgram,
  fetchRewardsSummary,
} from '../api.js'

function defaultRewardsForm() {
  return { scraper_login_id: null, financial_account_id: null, membership_id: '', program_name: '', program_type: 'points', unit_name: '', cents_per_unit: null, current_balance: null }
}

const rewards = shallowRef([])
const rewardsDialogVisible = shallowRef(false)
const rewardsDialogEdit = shallowRef(false)
const rewardsEditId = shallowRef(null)
const rewardsForm = shallowRef(defaultRewardsForm())
const rewardsTypes = [
  { label: 'Points', value: 'points' },
  { label: 'Miles', value: 'miles' },
  { label: 'Cashback', value: 'cashback' },
  { label: 'Other', value: 'other' },
]

export function useRewards() {
  const toast = useToast()

  async function loadRewards() {
    const data = await fetchRewardsSummary().catch(() => ({ programs: [] }))
    rewards.value = data.programs || []
  }

  function openRewardsDialog(reward = null) {
    if (reward) {
      rewardsDialogEdit.value = true
      rewardsEditId.value = reward.program_id
      rewardsForm.value = {
        scraper_login_id: reward.scraper_login_id,
        financial_account_id: reward.account_id,
        membership_id: reward.membership_id || '',
        program_name: reward.program_name,
        program_type: reward.program_type || 'points',
        unit_name: reward.unit_name || '',
        cents_per_unit: reward.cents_per_unit,
        current_balance: reward.balance,
      }
    } else {
      rewardsDialogEdit.value = false
      rewardsEditId.value = null
      rewardsForm.value = defaultRewardsForm()
    }
    rewardsDialogVisible.value = true
  }

  async function saveRewardsProgram(onSuccess) {
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
      if (onSuccess) await onSuccess()
    } catch (err) {
      toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 })
    }
  }

  return {
    rewards,
    rewardsDialogVisible,
    rewardsDialogEdit,
    rewardsEditId,
    rewardsForm,
    rewardsTypes,
    loadRewards,
    openRewardsDialog,
    saveRewardsProgram,
  }
}
