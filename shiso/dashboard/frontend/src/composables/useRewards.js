import { shallowRef } from 'vue'
import { useToast } from 'primevue/usetoast'
import {
  createRewardsProgram,
  updateRewardsProgram,
  fetchRewardsSummary,
} from '../api.js'

function defaultRewardsForm() {
  return { financial_account_id: null, program_name: '', program_type: 'points', unit_name: '', cents_per_unit: null }
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
        financial_account_id: reward.account_id,
        program_name: reward.program_name,
        program_type: reward.program_type || 'points',
        unit_name: reward.unit_name || '',
        cents_per_unit: reward.cents_per_unit,
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
