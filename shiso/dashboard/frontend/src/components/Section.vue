<template>
  <Panel v-bind="$attrs" toggleable :collapsed="isCollapsed" @toggle="onToggle">
    <template #header>
      <span class="font-semibold">
        {{ header }}
        <span v-if="count != null" class="text-surface-400 text-xs ml-1">({{ count }})</span>
      </span>
    </template>
    <template #toggleicon="{ collapsed: c }">
      <i :class="c ? 'pi pi-chevron-up' : 'pi pi-chevron-down'" />
    </template>
    <template v-if="$slots.icons" #icons>
      <slot name="icons" />
    </template>
    <slot />
  </Panel>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import Panel from 'primevue/panel'

const STORAGE_PREFIX = 'section:'

const props = defineProps({
  header: { type: String, required: true },
  count: { type: Number, default: null },
  collapsed: { type: Boolean, default: false },
  persistKey: { type: String, default: null },
})

const emit = defineEmits(['toggle', 'ready'])

function loadState() {
  if (!props.persistKey) return props.collapsed
  const stored = localStorage.getItem(STORAGE_PREFIX + props.persistKey)
  if (stored !== null) return stored === 'true'
  return props.collapsed
}

const isCollapsed = ref(loadState())

onMounted(() => {
  emit('ready', isCollapsed.value)
})

function onToggle(e) {
  isCollapsed.value = e.value
  if (props.persistKey) {
    localStorage.setItem(STORAGE_PREFIX + props.persistKey, String(e.value))
  }
  emit('toggle', e)
}
</script>
