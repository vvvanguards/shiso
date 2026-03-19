<template>
  <Dialog v-model:visible="visible" header="Interactive Auth" modal :style="{ width: '520px' }" @hide="emit('hide')">
    <div class="flex flex-col gap-4 pt-2">
      <div v-if="login" class="text-sm text-surface-300">
        <div class="font-medium">{{ login.institution || login.provider_key }}</div>
        <div class="text-xs text-surface-400">{{ login.username || login.label }}</div>
      </div>
      <Message :severity="sessionSeverity(session.status)" :closable="false">
        {{ session.message || 'Interactive auth is in progress.' }}
      </Message>
      <div v-if="session.status === 'awaiting_input'" class="flex flex-col gap-2">
        <label class="text-sm font-medium">Verification Code or Answer</label>
        <InputText
          v-model="response"
          placeholder="Enter the code, answer, or a short confirmation"
          fluid
          @keyup.enter="emit('submit', false)"
        />
        <div v-if="session.prompt" class="text-xs text-surface-400">
          {{ session.prompt }}
        </div>
      </div>
      <div v-else-if="session.status === 'running' || session.status === 'starting'" class="text-sm text-surface-300">
        Keep the browser window open. The agent will pause here again if it needs a code or answer from you.
      </div>
      <div v-else-if="session.status === 'skipped'" class="text-sm text-surface-300">
        This auth attempt was skipped. The login will stay in the attention list so you can retry later.
      </div>
    </div>
    <template #footer>
      <Button @click="visible = false" label="Close" severity="secondary" text />
      <Button
        v-if="session.status === 'awaiting_input'"
        @click="emit('submit', true)"
        :loading="responding"
        label="Skip for Now"
        severity="secondary"
      />
      <Button
        v-if="session.status === 'awaiting_input'"
        @click="emit('submit', false)"
        :disabled="!response.trim()"
        :loading="responding"
        label="Send to Agent"
        severity="success"
      />
    </template>
  </Dialog>
</template>

<script setup>
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'

defineProps({
  login: { type: Object, default: null },
  session: {
    type: Object,
    default: () => ({
      status: 'idle',
      message: 'No interactive auth session running.',
      prompt: null,
    }),
  },
  responding: { type: Boolean, default: false },
})

const visible = defineModel('visible', { type: Boolean, required: true })
const response = defineModel('response', { type: String, required: true })

const emit = defineEmits(['hide', 'submit'])

function sessionSeverity(status) {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'awaiting_input') return 'warn'
  return 'info'
}
</script>
