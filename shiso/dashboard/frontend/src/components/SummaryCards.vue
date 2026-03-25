<template>
  <div class="grid gap-4 grid-cols-3">
    <Card>
      <template #content>
        <div class="text-xs uppercase tracking-widest text-shiso-400">Assets</div>
        <div class="mt-1 text-2xl font-semibold text-accent-green">{{ money((summary.asset_total || 0) + (summary.total_rewards_value || 0)) }}</div>
        <div v-if="summary.total_rewards_value" class="text-xs text-shiso-400 mt-0.5">+ {{ money(summary.total_rewards_value) }} rewards</div>
      </template>
    </Card>
    <Card>
      <template #content>
        <div class="text-xs uppercase tracking-widest text-shiso-400">Liabilities</div>
        <div class="mt-1 text-2xl font-semibold text-accent-amber">{{ money(summary.debt_total) }}</div>
      </template>
    </Card>
    <Card>
      <template #content>
        <div class="text-xs uppercase tracking-widest text-shiso-400">Net Position</div>
        <div class="mt-1 text-2xl font-semibold" :class="(summary.net_balance || 0) >= 0 ? 'text-accent-green' : 'text-accent-red'">
          {{ signedMoney(summary.net_balance) }}
        </div>
      </template>
    </Card>
  </div>
</template>

<script setup>
import Card from 'primevue/card'
import { money, signedMoney } from '../helpers.js'

defineProps({
  summary: { type: Object, required: true },
})
</script>
