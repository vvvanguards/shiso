<template>
  <div class="mx-auto max-w-7xl space-y-6">
    <LoginsPanel
      :logins="logins"
      :loading="loginsLoading"
      :syncingAll="syncingAllLogins"
      :enabledCount="enabledLoginCount"
      :showDeleted="showDeleted"
      @add="openLoginDialog()"
      @syncAll="syncEnabledLogins"
      @sync="syncLoginRow"
      @edit="openLoginDialog"
      @toggle="toggleEnabled"
      @delete="confirmDeleteLogin"
      @toggleShowDeleted="showDeleted = !showDeleted; loadLogins()"
    />
  </div>
</template>

<script setup>
import LoginsPanel from '../components/LoginsPanel.vue'
import { useLogins } from '../composables/useLogins.js'

const {
  logins, loginsLoading, syncingAllLogins, showDeleted, enabledLoginCount,
  loginDialogVisible, loginDialogEdit, loginForm, providers, accountTypes, toolOptions,
  loadLogins, syncLoginRow, syncEnabledLogins,
  openLoginDialog, saveLogin, confirmDeleteLogin, toggleEnabled,
} = useLogins()
</script>
