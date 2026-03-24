<template>
  <Message 
    v-if="awaitingSessions.length > 0"
    severity="warn" 
    :closable="true"
    :pt="{
      root: { class: 'bg-amber-500/10 border-amber-500/30' },
      icon: { class: 'text-amber-400' }
    }"
  >
    <template #icon>
      <i class="pi pi-comments" />
    </template>
    <template #header>
      Agent Needs Help
    </template>
    <p class="text-sm text-shiso-200 mb-3">
      {{ awaitingSessions.length }} running agent(s) need your input to continue.
    </p>
    <div class="flex flex-wrap gap-2">
      <div v-for="session in awaitingSessions" :key="session.run_id" class="flex items-center gap-2 bg-shiso-900 rounded px-3 py-2">
        <Tag value="Awaiting Input" severity="warn" />
        <span class="font-medium">{{ session.provider_key }}</span>
        <span class="text-xs text-shiso-400 max-w-48 truncate">{{ session.prompt }}</span>
        <Button
          @click="$emit('respond', session)"
          label="Respond"
          icon="pi pi-reply"
          severity="success"
          size="small"
        />
      </div>
    </div>
  </Message>
</template>

<script setup>
import { computed } from 'vue'
import Button from 'primevue/button'
import Message from 'primevue/message'
import Tag from 'primevue/tag'

const props = defineProps({
  sessions: { type: Array, required: true },
})

defineEmits(['respond'])

const awaitingSessions = computed(() =>
  props.sessions.filter(s => s.status === 'awaiting_input')
)
</script>
