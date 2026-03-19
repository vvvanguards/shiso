import { ref } from 'vue'
import { useToast } from 'primevue/usetoast'
import {
  fetchTools,
  fetchToolDefinition,
  draftToolDefinition as apiDraftToolDefinition,
  fetchToolRuns,
  fetchWorkflowSuggestions,
  saveToolDefinition as apiSaveToolDefinition,
  deleteToolDefinition as apiDeleteToolDefinition,
  updateWorkflowSuggestionStatus as apiUpdateWorkflowSuggestionStatus,
} from '../api.js'

export function useTools() {
  const toast = useToast()

  const tools = ref([])
  const toolRuns = ref([])
  const workflowSuggestions = ref([])
  const selectedToolKey = ref(null)
  const toolDialogVisible = ref(false)
  const toolDialogEdit = ref(false)
  const toolDialogLoading = ref(false)
  const toolEditKey = ref('')
  const toolForm = ref(defaultToolForm())
  const activeToolSuggestionId = ref(null)
  const toolDraftDialogVisible = ref(false)
  const toolDraftLoading = ref(false)
  const toolDraftForm = ref(defaultToolDraftForm())

  function defaultToolForm() {
    return {
      key: '',
      name: '',
      description: '',
      prompt_template: '',
      result_key: 'items',
      output_schema_json: '[]',
    }
  }

  function defaultToolDraftForm() {
    return {
      brief: '',
      existing_key: null,
      example_items_json: '[]',
    }
  }

  async function loadToolRuns(toolKey) {
    selectedToolKey.value = toolKey
    try {
      toolRuns.value = await fetchToolRuns(toolKey)
    } catch (err) {
      toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 })
    }
  }

  function closeToolDialog() {
    toolDialogVisible.value = false
    activeToolSuggestionId.value = null
  }

  async function openToolDialog(tool = null) {
    toolDialogLoading.value = true
    if (!tool) {
      activeToolSuggestionId.value = null
      toolDialogEdit.value = false
      toolEditKey.value = ''
      toolForm.value = defaultToolForm()
      toolDialogVisible.value = true
      toolDialogLoading.value = false
      return
    }

    try {
      activeToolSuggestionId.value = null
      const definition = await fetchToolDefinition(tool.tool_key)
      toolDialogEdit.value = true
      toolEditKey.value = definition.key
      toolForm.value = {
        key: definition.key,
        name: definition.name,
        description: definition.description || '',
        prompt_template: definition.prompt_template || '',
        result_key: definition.result_key || 'items',
        output_schema_json: JSON.stringify(definition.output_schema_json || [], null, 2),
      }
      toolDialogVisible.value = true
    } catch (err) {
      toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 })
    } finally {
      toolDialogLoading.value = false
    }
  }

  function openToolDraftDialog(tool = null) {
    activeToolSuggestionId.value = null
    toolDraftForm.value = {
      brief: tool ? `Improve the ${tool.display_name || tool.tool_key} workflow.` : '',
      existing_key: tool?.tool_key || null,
      example_items_json: '[]',
    }
    toolDraftDialogVisible.value = true
  }

  function reviewWorkflowSuggestion(suggestion) {
    const draft = suggestion.suggested_definition
    activeToolSuggestionId.value = suggestion.id
    toolDialogEdit.value = true
    toolEditKey.value = draft.key
    toolForm.value = {
      key: draft.key,
      name: draft.name,
      description: draft.description || '',
      prompt_template: draft.prompt_template || '',
      result_key: draft.result_key || 'items',
      output_schema_json: JSON.stringify(draft.output_schema_json || [], null, 2),
    }
    toolDialogVisible.value = true
  }

  async function dismissWorkflowSuggestion(suggestion) {
    try {
      await apiUpdateWorkflowSuggestionStatus(suggestion.id, 'dismissed')
      toast.add({ severity: 'info', summary: 'Dismissed', detail: suggestion.tool_key, life: 3000 })
      await loadToolsData()
    } catch (err) {
      toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 5000 })
    }
  }

  async function saveToolDefinition() {
    let parsedSchema = []
    try {
      parsedSchema = JSON.parse(toolForm.value.output_schema_json || '[]')
    } catch {
      toast.add({ severity: 'error', summary: 'Invalid Schema', detail: 'Output schema JSON must be valid.', life: 5000 })
      return
    }

    if (!Array.isArray(parsedSchema)) {
      toast.add({ severity: 'error', summary: 'Invalid Schema', detail: 'Output schema JSON must be an array of field definitions.', life: 5000 })
      return
    }

    const key = (toolDialogEdit.value ? toolEditKey.value : toolForm.value.key).trim()
    if (!key) {
      toast.add({ severity: 'error', summary: 'Missing Key', detail: 'Tool key is required.', life: 4000 })
      return
    }

    try {
      const suggestionId = activeToolSuggestionId.value
      await apiSaveToolDefinition(key, {
        name: toolForm.value.name.trim(),
        description: toolForm.value.description.trim(),
        prompt_template: toolForm.value.prompt_template,
        result_key: toolForm.value.result_key.trim() || 'items',
        output_schema_json: parsedSchema,
      })
      toolDialogVisible.value = false
      activeToolSuggestionId.value = null
      if (suggestionId) {
        try {
          await apiUpdateWorkflowSuggestionStatus(suggestionId, 'applied')
        } catch (statusErr) {
          toast.add({ severity: 'warn', summary: 'Tool Saved', detail: `Saved ${key}, but could not mark the suggestion applied.`, life: 5000 })
        }
      }
      toast.add({ severity: 'success', summary: toolDialogEdit.value ? 'Updated' : 'Created', detail: key, life: 3000 })
      await loadToolsData()
    } catch (err) {
      toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 5000 })
    }
  }

  async function runToolDraft() {
    let parsedExamples = []
    try {
      parsedExamples = JSON.parse(toolDraftForm.value.example_items_json || '[]')
    } catch {
      toast.add({ severity: 'error', summary: 'Invalid Examples', detail: 'Example items JSON must be valid.', life: 5000 })
      return
    }

    if (!Array.isArray(parsedExamples)) {
      toast.add({ severity: 'error', summary: 'Invalid Examples', detail: 'Example items JSON must be an array.', life: 5000 })
      return
    }

    if (!toolDraftForm.value.brief.trim()) {
      toast.add({ severity: 'error', summary: 'Missing Brief', detail: 'Describe what the tool should do.', life: 4000 })
      return
    }

    toolDraftLoading.value = true
    try {
      const draft = await apiDraftToolDefinition({
        brief: toolDraftForm.value.brief,
        existing_key: toolDraftForm.value.existing_key || null,
        example_items: parsedExamples,
      })
      activeToolSuggestionId.value = null
      toolDialogEdit.value = false
      toolEditKey.value = draft.key
      toolForm.value = {
        key: draft.key,
        name: draft.name,
        description: draft.description || '',
        prompt_template: draft.prompt_template || '',
        result_key: draft.result_key || 'items',
        output_schema_json: JSON.stringify(draft.output_schema_json || [], null, 2),
      }
      toolDraftDialogVisible.value = false
      toolDialogVisible.value = true
      toast.add({ severity: 'success', summary: 'Draft Ready', detail: draft.rationale || draft.name, life: 4000 })
    } catch (err) {
      toast.add({ severity: 'error', summary: 'Draft Failed', detail: err.message, life: 5000 })
    } finally {
      toolDraftLoading.value = false
    }
  }

  function confirmDeleteTool(tool) {
    return new Promise((resolve) => {
      resolve({
        message: `Delete DB-backed definition for "${tool.display_name}"? Built-in tools will fall back to their default code definition.`,
        header: 'Confirm Delete',
        icon: 'pi pi-trash',
        acceptClass: 'p-button-danger',
        accept: async () => {
          try {
            await apiDeleteToolDefinition(tool.tool_key)
            toast.add({ severity: 'info', summary: 'Deleted', detail: tool.tool_key, life: 3000 })
            if (selectedToolKey.value === tool.tool_key) toolRuns.value = []
            await loadToolsData()
          } catch (err) {
            toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 5000 })
          }
        },
      })
    })
  }

  async function loadToolsData() {
    try {
      const [t, suggestions] = await Promise.all([
        fetchTools(),
        fetchWorkflowSuggestions().catch(() => []),
      ])
      tools.value = t
      workflowSuggestions.value = suggestions
    } catch (err) {
      toast.add({ severity: 'error', summary: 'Error', detail: err.message, life: 4000 })
    }
  }

  return {
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
    confirmDeleteTool,
    loadToolsData,
  }
}