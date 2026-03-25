<script setup>
import { computed, nextTick, onMounted, ref, watch, inject } from 'vue'
import Panel from 'primevue/panel'

const STORAGE_PREFIX = 'section:'

const props = defineProps({
  header: { type: String, required: true },
  count: { type: Number, default: null },
  collapsed: { type: Boolean, default: false },
  persistKey: { type: String, default: null },
})

const emit = defineEmits(['toggle', 'ready', 'expanded'])

const activeSection = inject('activeSection', null)

const sectionId = computed(() => props.persistKey)

const isCollapsed = computed(() => {
  if (activeSection?.value && sectionId.value) {
    return activeSection.value !== sectionId.value
  }
  if (!props.persistKey) return props.collapsed
  const stored = localStorage.getItem(STORAGE_PREFIX + props.persistKey)
  if (stored !== null) return stored === 'true'
  return props.collapsed
})

function loadState() {
  if (!props.persistKey) return props.collapsed
  const stored = localStorage.getItem(STORAGE_PREFIX + props.persistKey)
  if (stored !== null) return stored === 'true'
  return props.collapsed
}

const internalCollapsed = ref(loadState())

onMounted(() => {
  emit('ready', isCollapsed.value)
})

watch(activeSection, (newVal) => {
  if (newVal && sectionId.value && newVal === sectionId.value) {
    internalCollapsed.value = false
    emit('expanded', sectionId.value)
  }
})

function onToggle(e) {
  internalCollapsed.value = e.value
  if (props.persistKey) {
    localStorage.setItem(STORAGE_PREFIX + props.persistKey, String(e.value))
  }
  emit('toggle', e)
}
</script>

<template>
  <Panel v-bind="$attrs" toggleable :collapsed="isCollapsed" @toggle="onToggle">
    <template #header>
      <span class="font-semibold">
        {{ header }}
        <span v-if="count != null" class="text-shiso-400 text-xs ml-1">({{ count }})</span>
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
