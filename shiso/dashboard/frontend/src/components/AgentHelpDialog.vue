<template>
  <Dialog v-model:visible="visible" header="Agent Needs Help" modal :style="{ width: '520px' }" @hide="emit('hide')">
    <div class="flex flex-col gap-4 pt-2">
      <div v-if="session" class="text-sm text-shiso-300">
        <div class="font-medium font-body">{{ session.provider_key }}</div>
        <div class="text-xs text-shiso-400">Run #{{ session.run_id }}</div>
      </div>

      <Message :severity="severityFor(session?.status)" :closable="false">
        {{ session?.message || 'Agent session active.' }}
      </Message>

      <div v-if="session?.status === 'awaiting_input'" class="flex flex-col gap-2">
        <label class="text-sm font-medium font-body">{{ session.prompt || 'The agent needs your input' }}</label>
        <InputText
          v-model="response"
          placeholder="Type your response..."
          fluid
          @keyup.enter="emit('submit', false)"
        />
      </div>

      <div v-else-if="session?.status === 'running'" class="text-sm text-shiso-300">
        The agent is working. It will pause here if it needs your help.
      </div>

      <div v-else-if="session?.status === 'completed'" class="text-sm text-shiso-300">
        Agent finished successfully.
      </div>

      <div v-else-if="session?.status === 'failed'" class="text-sm text-shiso-300">
        Agent encountered an error.
      </div>
    </div>

    <template #footer>
      <Button @click="visible = false" label="Close" severity="secondary" text />
      <Button
        v-if="session?.status === 'awaiting_input'"
        @click="emit('submit', true)"
        :loading="responding"
        label="Skip"
        severity="secondary"
      />
      <Button
        v-if="session?.status === 'awaiting_input'"
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
  session: { type: Object, default: null },
  responding: { type: Boolean, default: false },
})

const visible = defineModel('visible', { type: Boolean, required: true })
const response = defineModel('response', { type: String, required: true })

const emit = defineEmits(['hide', 'submit'])

function severityFor(status) {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'awaiting_input') return 'warn'
  return 'info'
}
</script>
