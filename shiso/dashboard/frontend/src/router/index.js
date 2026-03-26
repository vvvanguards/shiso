import { createRouter, createWebHistory } from 'vue-router'

import OverviewView from '../views/OverviewView.vue'
import FinancesView from '../views/FinancesView.vue'
import AccountsView from '../views/AccountsView.vue'
import ImportView from '../views/ImportView.vue'
import ZeroBalanceView from '../views/ZeroBalanceView.vue'

const routes = [
  { path: '/', redirect: '/overview' },
  { path: '/overview', name: 'overview', component: OverviewView },
  { path: '/finances', name: 'finances', component: FinancesView },
  { path: '/accounts', name: 'accounts', component: AccountsView },
  { path: '/import', name: 'import', component: ImportView },
  { path: '/zero-balance', name: 'zero-balance', component: ZeroBalanceView },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
