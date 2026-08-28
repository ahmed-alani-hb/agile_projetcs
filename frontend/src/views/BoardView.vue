<template>
  <div class="h-full overflow-x-auto overflow-y-hidden">
    <div v-if="board.loading && !columns.length" class="py-16 text-center text-sm text-gray-500">
      Loading board…
    </div>
    <div v-else class="flex h-full gap-3 px-4 py-4 sm:px-6">
      <KanbanColumn
        v-for="column in columns"
        :key="column.status"
        :column="column"
        :is-visible="matchesFilters"
        @card-moved="onCardMoved"
        @open-task="(task) => $emit('open-task', task)"
        @quick-add="quickAdd"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { createResource } from 'frappe-ui'
import KanbanColumn from '@/components/KanbanColumn.vue'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  project: { type: String, required: true },
  filters: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['open-task', 'progress'])

const columns = ref([])

const board = createResource({
  url: 'agile_projects.api.get_board',
  makeParams: () => ({ project: props.project }),
  auto: true,
  onSuccess(data) {
    columns.value = data.columns.map((column) => ({
      status: column.status,
      tasks: [...column.tasks],
    }))
    if (data.project?.percent_complete != null) {
      emit('progress', data.project.percent_complete)
    }
  },
  onError(err) {
    toast({ title: 'Failed to load board', text: errorMessage(err), type: 'error' })
  },
})

watch(() => props.project, () => board.reload())

// Filtering is client-side here so drag-and-drop keeps working on the full
// column model; the other views filter server-side.
function matchesFilters(task) {
  const f = props.filters || {}
  if (f.status && task.status !== f.status) return false
  if (f.sme_responsible && task.sme_responsible !== f.sme_responsible) return false
  if (f.priority && task.priority !== f.priority) return false
  if (f.overdue) {
    if (task.status === 'Done' || !task.exp_end_date) return false
    if (new Date(task.exp_end_date) >= new Date(new Date().toDateString())) return false
  }
  if (f.search) {
    const needle = f.search.toLowerCase()
    if (
      !(task.subject || '').toLowerCase().includes(needle) &&
      !(task.name || '').toLowerCase().includes(needle)
    ) {
      return false
    }
  }
  return true
}

const updateStatus = createResource({ url: 'agile_projects.api.update_task_status' })
const reorder = createResource({ url: 'agile_projects.views.reorder_column' })

function persistOrder(status) {
  const column = columns.value.find((c) => c.status === status)
  if (!column) return
  reorder
    .submit({
      project: props.project,
      status,
      task_names: column.tasks.map((t) => t.name),
    })
    .catch(() => {
      /* ordering is best-effort; a failure just means the next load re-sorts */
    })
}

function onCardMoved(evt, status) {
  // Reordering inside a column: persist order only, no status change.
  if (evt.moved) {
    persistOrder(status)
    return
  }
  if (!evt.added) return

  const task = evt.added.element
  const previousStatus = task.status
  task.status = status
  updateStatus
    .submit({ task: task.name, status })
    .then((data) => {
      if (data.percent_complete != null) emit('progress', data.percent_complete)
      persistOrder(status)
      board.reload()
    })
    .catch((err) => {
      task.status = previousStatus
      toast({ title: 'Move rejected', text: errorMessage(err), type: 'error', timeout: 8000 })
      board.reload()
    })
}

const createTask = createResource({ url: 'agile_projects.api.create_task' })

function quickAdd(status, subject) {
  createTask
    .submit({ project: props.project, subject, status })
    .then(() => {
      toast({ title: 'Task created', type: 'success', timeout: 2500 })
      board.reload()
    })
    .catch((err) => {
      toast({ title: 'Could not create task', text: errorMessage(err), type: 'error' })
    })
}

defineExpose({ reload: () => board.reload() })
</script>
