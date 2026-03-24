<template>
  <Message 
    v-if="activeLogins.length > 0"
    severity="error" 
    :closable="true"
    :pt="{
      root: { class: 'bg-accent-red/10 border-accent-red/30' },
      icon: { class: 'text-accent-red' }
    }"
  >
    <template #icon>
      <i class="pi pi-exclamation-triangle" />
    </template>
    <template #header>
      Attention Required
    </template>
    <p class="text-sm text-shiso-200 mb-3">
      {{ problemLogins.length }} login(s) need authentication. Interactive login required to sync these accounts.
    </p>
    <div class="flex flex-wrap gap-2">
      <div v-for="login in activeLogins" :key="login.id" class="flex items-center gap-2 bg-shiso-900 rounded px-3 py-2">
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
        <Button
          @click="dismissLogin(login.id)"
          icon="pi pi-times"
          text
          size="small"
          severity="secondary"
          v-tooltip="'Dismiss for this session'"
        />
      </div>
    </div>
  </Message>
</template>

<script setup>
import { ref, computed } from 'vue'
import Button from 'primevue/button'
import Message from 'primevue/message'
import Tag from 'primevue/tag'

const props = defineProps({
  problemLogins: { type: Array, required: true },
  authLoading: { type: Object, required: true },
})

defineEmits(['resolve'])

const dismissedIds = ref(new Set())

const activeLogins = computed(() => 
  props.problemLogins.filter(l => !dismissedIds.value.has(l.id))
)

function dismissLogin(id) {
  dismissedIds.value.add(id)
}
</script>
