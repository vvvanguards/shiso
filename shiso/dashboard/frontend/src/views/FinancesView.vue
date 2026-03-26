<template>
  <div class="mx-auto max-w-7xl space-y-6">
    <section id="liabilities">
      <LiabilitiesSection
        :rows="liabilityRows"
        v-model:filters="tableFilters"
        :logins="logins"
        @sync="(s) => dashboard.syncSnapshotRow(s, logins, syncLoginRow)"
        @edit="(s) => dashboard.editSnapshotRow(s, logins, openLoginDialog)"
      />
    </section>

    <section id="bills">
      <BillsSection
        :rows="billRows"
        v-model:filters="tableFilters"
        :logins="logins"
        @sync="(s) => dashboard.syncSnapshotRow(s, logins, syncLoginRow)"
        @edit="(s) => dashboard.editSnapshotRow(s, logins, openLoginDialog)"
        @toggle-paid="handleTogglePaid"
      />
    </section>

    <section id="promos">
      <PromosPanel
        :promos="promos"
        :loading="loading"
        @add="openPromoDialog"
        @edit="openPromoDialog"
        @delete="confirmDeletePromo($event, loadAll)"
      />
    </section>

    <section id="assets">
      <AssetsSection
        :rows="assetRows"
        v-model:filters="tableFilters"
        :logins="logins"
        @sync="(s) => dashboard.syncSnapshotRow(s, logins, syncLoginRow)"
        @edit="(s) => dashboard.editSnapshotRow(s, logins, openLoginDialog)"
      />
    </section>

    <section id="rewards">
      <RewardsSection
        :rows="rewards"
        @add="openRewardsDialog"
        @edit="openRewardsDialog"
      />
    </section>
  </div>
</template>

<script setup>
import LiabilitiesSection from '../components/LiabilitiesSection.vue'
import BillsSection from '../components/BillsSection.vue'
import PromosPanel from '../components/PromosPanel.vue'
import AssetsSection from '../components/AssetsSection.vue'
import RewardsSection from '../components/RewardsSection.vue'

import { useDashboard } from '../composables/useDashboard.js'
import { useLogins } from '../composables/useLogins.js'
import { usePromos } from '../composables/usePromos.js'
import { useRewards } from '../composables/useRewards.js'

const dashboard = useDashboard()
const { tableFilters, billRows, assetRows, liabilityRows, toggleSnapshotPaidStatus } = dashboard

const { logins, syncLoginRow, openLoginDialog, loadLogins } = useLogins()
const { promos, openPromoDialog, confirmDeletePromo, loadPromos } = usePromos()
const { rewards, openRewardsDialog, loadRewards } = useRewards()

function handleTogglePaid(snapshotId, newIsPaid) {
  toggleSnapshotPaidStatus(snapshotId, newIsPaid)
}

async function loadAll() {
  await Promise.all([loadDashboard(), loadLogins(), loadPromos(), loadRewards()])
}
</script>
