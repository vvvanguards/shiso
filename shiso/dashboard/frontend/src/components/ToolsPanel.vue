<template>
  <Section v-if="false" header="Tools" :collapsed="true" persistKey="tools">
    <template #icons>
      <Button @click.stop="openToolDraftDialog()" icon="pi pi-bolt" severity="help" size="small" text rounded v-tooltip.top="'Draft tool with AI'" />
      <Button @click.stop="openToolDialog()" icon="pi pi-plus" severity="success" size="small" text rounded v-tooltip.top="'Create tool'" />
    </template>
    <div v-if="workflowSuggestions.length" class="mb-4 rounded-lg border border-amber-800/70 bg-amber-950/20 p-4">
      <div class="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 class="text-sm uppercase tracking-widest text-amber-300">AI Suggestions</h3>
          <p class="mt-1 text-sm text-surface-300">Weak or failed tool runs can draft revisions automatically. Review a suggestion, then save it into the tool definition when it looks right.</p>
        </div>
        <Tag :value="`${workflowSuggestions.length} Open`" severity="warn" />
      </div>
      <DataTable :value="workflowSuggestions" stripedRows size="small">
        <Column header="Tool">
          <template #body="{ data }">
            <div class="font-medium">{{ data.suggested_definition.name || data.tool_key }}</div>
            <div class="text-xs text-surface-400">{{ data.tool_key }} · {{ data.provider_key }}</div>
          </template>
        </Column>
        <Column field="trigger_reason" header="Why" />
        <Column field="created_at" header="Created" sortable>
          <template #body="{ data }">{{ relativeTime(data.created_at) }}</template>
        </Column>
        <Column header="" style="width: 9rem">
          <template #body="{ data }">
            <div class="flex gap-1">
              <Button @click="reviewWorkflowSuggestion(data)" icon="pi pi-pencil" severity="help" text rounded size="small" v-tooltip.top="'Review draft'" />
              <Button @click="dismissWorkflowSuggestion(data)" icon="pi pi-times" severity="secondary" text rounded size="small" v-tooltip.top="'Dismiss suggestion'" />
            </div>
          </template>
        </Column>
      </DataTable>
    </div>
    <div v-if="!tools.length" class="py-4 text-center text-surface-400">No tools registered.</div>
    <div v-else class="space-y-4">
      <DataTable :value="tools" stripedRows size="small">
        <Column field="display_name" header="Tool" sortable>
          <template #body="{ data }">
            <div class="font-medium">{{ data.display_name }}</div>
            <div class="text-xs text-surface-400">{{ data.tool_key }}</div>
          </template>
        </Column>
        <Column field="description" header="Description" />
        <Column field="source" header="Source" sortable>
          <template #body="{ data }">
            <Tag :value="data.source === 'db' ? 'Runtime' : 'Code'" :severity="data.source === 'db' ? 'success' : 'secondary'" />
          </template>
        </Column>
        <Column header="" style="width: 8rem">
          <template #body="{ data }">
            <div class="flex gap-1">
              <Button @click="loadToolRuns(data.tool_key)" icon="pi pi-list" severity="secondary" text rounded size="small" v-tooltip.top="'View runs'" />
              <Button @click="openToolDraftDialog(data)" icon="pi pi-bolt" severity="help" text rounded size="small" v-tooltip.top="'Draft revision with AI'" />
              <Button @click="openToolDialog(data)" icon="pi pi-pencil" severity="secondary" text rounded size="small" :loading="toolDialogLoading && toolEditKey === data.tool_key" v-tooltip.top="'Edit tool'" />
              <Button @click="handleDeleteTool(data)" icon="pi pi-trash" severity="danger" text rounded size="small" v-tooltip.top="'Delete DB definition'" />
            </div>
          </template>
        </Column>
      </DataTable>

      <div v-if="selectedToolKey && toolRuns.length" class="mt-4">
        <h3 class="text-sm uppercase tracking-widest text-surface-400 mb-2">Recent Runs: {{ selectedToolKey }}</h3>
        <DataTable :value="toolRuns" stripedRows size="small" :rows="10" :paginator="toolRuns.length > 10">
          <Column field="created_at" header="Date" sortable>
            <template #body="{ data }">{{ relativeTime(data.created_at) }}</template>
          </Column>
          <Column field="provider_key" header="Provider" sortable />
          <Column field="items_count" header="Items" sortable />
          <Column header="Output">
            <template #body="{ data }">
              <span class="text-xs text-surface-400 truncate block max-w-[300px]">{{ JSON.stringify(data.output_json).substring(0, 100) }}...</span>
            </template>
          </Column>
        </DataTable>
      </div>
    </div>
  </Section>

  <!-- Tool Draft Dialog -->
  <Dialog v-if="false" v-model:visible="toolDraftDialogVisible" header="Draft Tool with AI" modal :style="{ width: '720px' }">
    <div class="flex flex-col gap-4 pt-2">
      <Message severity="secondary" :closable="false">
        Describe the workflow in plain English. If you are revising an existing tool and leave examples empty, Shiso will seed the draft from recent tool runs when it can.
      </Message>
      <div v-if="toolDraftForm.existing_key" class="flex flex-col gap-1">
        <label class="text-sm font-medium">Revising Tool</label>
        <InputText :model-value="toolDraftForm.existing_key" disabled fluid />
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Brief</label>
        <Textarea v-model="toolDraftForm.brief" rows="5" autoResize fluid />
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Example Items JSON</label>
        <Textarea v-model="toolDraftForm.example_items_json" rows="10" autoResize fluid />
        <div class="text-xs text-surface-400">
          Optional. Use a JSON array of sample items to steer the schema, like
          <code>[{"unit":"1A","rent":1200.0}]</code>
        </div>
      </div>
    </div>
    <template #footer>
      <Button @click="toolDraftDialogVisible = false" label="Cancel" severity="secondary" text />
      <Button @click="runToolDraft" label="Draft" severity="help" :loading="toolDraftLoading" />
    </template>
  </Dialog>

  <!-- Tool Dialog -->
  <Dialog v-if="false" v-model:visible="toolDialogVisible" :header="toolDialogEdit ? 'Edit Tool' : 'Create Tool'" modal :style="{ width: '760px' }">
    <div class="flex flex-col gap-4 pt-2">
      <Message v-if="activeToolSuggestionId" severity="warn" :closable="false">
        This draft came from an analyst suggestion after a weak run. Review it before saving.
      </Message>
      <div class="grid grid-cols-2 gap-4">
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium">Tool Key</label>
          <InputText v-model="toolForm.key" :disabled="toolDialogEdit" placeholder="e.g. rent_roll" fluid />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm font-medium">Result Key</label>
          <InputText v-model="toolForm.result_key" placeholder="e.g. rows" fluid />
        </div>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Display Name</label>
        <InputText v-model="toolForm.name" placeholder="e.g. Rent Roll" fluid />
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Description</label>
        <InputText v-model="toolForm.description" placeholder="Short description" fluid />
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Prompt Template</label>
        <Textarea v-model="toolForm.prompt_template" rows="10" autoResize fluid />
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-sm font-medium">Output Schema JSON</label>
        <Textarea v-model="toolForm.output_schema_json" rows="10" autoResize fluid />
        <div class="text-xs text-surface-400">
          Use an array of field specs like
          <code>[{"name":"unit","type":"str"},{"name":"rent","type":"float","nullable":true}]</code>
        </div>
      </div>
    </div>
    <template #footer>
      <Button @click="closeToolDialog" label="Cancel" severity="secondary" text />
      <Button @click="saveToolDefinition" :label="toolDialogEdit ? 'Update' : 'Create'" severity="success" />
    </template>
  </Dialog>
</template>

<script setup>
import { useConfirm } from 'primevue/useconfirm'
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import Textarea from 'primevue/textarea'
import Section from './Section.vue'
import { useTools } from '../composables/useTools.js'
import { relativeTime } from '../helpers.js'

const confirm = useConfirm()
const {
  tools,
  toolRuns,
  workflowSuggestions,
  selectedToolKey,
  toolDialogVisible,
  toolDialogEdit,
  toolDialogLoading,
  toolEditKey,
  toolForm,
  activeToolSuggestionId,
  toolDraftDialogVisible,
  toolDraftLoading,
  toolDraftForm,
  loadToolRuns,
  closeToolDialog,
  openToolDialog,
  openToolDraftDialog,
  reviewWorkflowSuggestion,
  dismissWorkflowSuggestion,
  saveToolDefinition,
  runToolDraft,
} = useTools()

function handleDeleteTool(tool) {
  confirm.require({
    message: `Delete DB-backed definition for "${tool.display_name}"? Built-in tools will fall back to their default code definition.`,
    header: 'Confirm Delete',
    icon: 'pi pi-trash',
    acceptClass: 'p-button-danger',
    accept: async () => {
      const { deleteToolDefinition } = await import('../api.js')
      try {
        await deleteToolDefinition(tool.tool_key)
        if (selectedToolKey.value === tool.tool_key) toolRuns.value = []
        await tools.loadToolsData?.()
      } catch (err) {
        // Error handled in composable
      }
    },
  })
}
</script>