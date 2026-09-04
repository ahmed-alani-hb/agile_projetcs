<template>
  <div class="h-full overflow-x-auto overflow-y-hidden">
    <div v-if="board.loading && !columns.length" class="py-16 text-center text-sm text-gray-500">
      Loading modules…
    </div>

    <div v-else-if="!loadingOrHasModules" class="px-6 py-16 text-center">
      <p class="text-sm font-medium text-gray-700">No modules yet</p>
      <p class="mx-auto mt-1 max-w-md text-sm text-gray-500">
        A module is an area of the ERP rollout — Accounting, Inventory, CRM — that moves through
        the delivery gates. Add one to start planning against it.
      </p>
      <Button class="mt-4" variant="solid" size="sm" @click="showNew = true">Add module</Button>
    </div>

    <div v-else class="flex h-full gap-3 px-4 py-4 sm:px-6">
      <KanbanColumn
        v-for="column in columns"
        :key="column.gate"
        :column="column"
        key-field="gate"
        items-key="modules"
        :meta-map="GATE_META"
        fallback-meta-key="Configure"
        group="modules"
        :stat="gateStat"
        stat-title="Tasks done across this column"
        :can-add="column.gate === GATES[0]"
        add-label="+ Add module"
        @card-moved="onCardMoved"
        @open-task="openModule"
        @quick-add="() => (showNew = true)"
      >
        <template #card="{ item, open }">
          <ModuleCard :module="item" @open="open" />
        </template>
      </KanbanColumn>
    </div>

    <NewModuleDialog v-model="showNew" :project="project" @created="onCreated" />

    <ModuleDetailModal
      v-model="showDetail"
      :module="selectedModule"
      @changed="board.reload()"
      @progress="(value) => emit('progress', value)"
    />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Button, createResource } from 'frappe-ui'
import KanbanColumn from '@/components/KanbanColumn.vue'
import ModuleCard from '@/components/ModuleCard.vue'
import NewModuleDialog from '@/components/NewModuleDialog.vue'
import ModuleDetailModal from '@/components/ModuleDetailModal.vue'
import { GATES, GATE_META } from '@/utils/statuses'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  project: { type: String, required: true },
})

const emit = defineEmits(['progress'])

const columns = ref([])
const showNew = ref(false)
const showDetail = ref(false)
const selectedModule = ref(null)

const board = createResource({
  url: 'agile_projects.modules.get_modules',
  makeParams: () => ({ project: props.project }),
  auto: true,
  onSuccess(data) {
    // Detached copies so drag mutation stays local until the server agrees.
    columns.value = data.columns.map((column) => ({
      gate: column.gate,
      modules: [...column.modules],
    }))
    if (data.project?.percent_complete != null) {
      emit('progress', data.project.percent_complete)
    }
  },
  onError(err) {
    toast({ title: 'Failed to load modules', text: errorMessage(err), type: 'error' })
  },
})

watch(
  () => props.project,
  () => board.reload()
)

const loadingOrHasModules = computed(
  () => board.loading || columns.value.some((column) => column.modules.length)
)

function gateStat(modules) {
  const done = modules.reduce((sum, m) => sum + (m.done_tasks || 0), 0)
  const total = modules.reduce((sum, m) => sum + (m.total_tasks || 0), 0)
  return total ? `${done}/${total}` : null
}

const updateGate = createResource({ url: 'agile_projects.modules.update_module_gate' })
const reorder = createResource({ url: 'agile_projects.modules.reorder_gate' })

function persistOrder(gate) {
  const column = columns.value.find((c) => c.gate === gate)
  if (!column) return
  reorder
    .submit({
      project: props.project,
      gate,
      module_names: column.modules.map((m) => m.name),
    })
    // Ordering is best-effort; a failure just means the next load re-sorts.
    .catch(() => {})
}

function onCardMoved(evt, gate) {
  if (evt.moved) {
    persistOrder(gate)
    return
  }
  if (!evt.added) return

  const module = evt.added.element
  const previousGate = module.gate
  module.gate = gate
  updateGate
    .submit({ module: module.name, gate })
    .then((data) => {
      if (data.percent_complete != null) emit('progress', data.percent_complete)
      persistOrder(gate)
      board.reload()
    })
    .catch((err) => {
      // vuedraggable has already spliced the card between the two arrays, so
      // restoring the field is not enough — the board has to reload.
      module.gate = previousGate
      toast({
        title: 'Gate move rejected',
        text: errorMessage(err),
        type: 'error',
        timeout: 8000,
      })
      board.reload()
    })
}

function openModule(module) {
  selectedModule.value = module
  showDetail.value = true
}

function onCreated() {
  showNew.value = false
  board.reload()
}

defineExpose({ reload: () => board.reload() })
</script>
