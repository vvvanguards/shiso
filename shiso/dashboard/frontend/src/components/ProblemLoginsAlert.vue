<template>
  <div v-if="problemLogins.length > 0" class="bg-accent-red/10 border border-accent-red/30 rounded-lg p-4">
    <div class="flex items-start gap-3">
      <i class="pi pi-exclamation-triangle text-accent-red text-xl mt-0.5" />
      <div class="flex-1">
        <h3 class="text-lg font-semibold text-accent-red mb-2 font-body">Attention Required</h3>
        <p class="text-sm text-shiso-200 mb-3">
          {{ problemLogins.length }} login(s) need authentication. Interactive login required to sync these accounts.
        </p>
        <div class="flex flex-wrap gap-2">
          <div v-for="login in problemLogins" :key="login.id" class="flex items-center gap-2 bg-shiso-900 rounded px-3 py-2">
            <Tag
              :value="login.last_auth_status === 'needs_2fa' ? '2FA Required' : 'Login Failed'"
              :severity="login.last_auth_status === 'needs_2fa' ? 'warn' : 'danger'"
            />
            <span class="font-medium">{{ login.institution || login.provider_key }}</span>
            <span class="text-xs text-shiso-400">{{ login.username || login.label }}</span>
            <Button
              @click="$emit('resolve', login)"
              :loading="authLoading[login.id]"
              :disabled="authLoading[login.id]"
              label="Resolve 2FA"
              icon="pi pi-sign-in"
              severity="success"
              size="small"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import Button from 'primevue/button'
import Tag from 'primevue/tag'

defineProps({
  problemLogins: { type: Array, required: true },
  authLoading: { type: Object, required: true },
})

defineEmits(['resolve'])
</script>
