<template>
  <div class="flex h-full flex-col">
    <AppHeader>
      <div class="flex min-w-0 items-center gap-3">
        <router-link to="/" class="shrink-0 text-sm text-gray-500 hover:text-gray-800">←</router-link>
        <div class="min-w-0">
          <p class="truncate text-sm font-semibold text-gray-900">
            {{ board.data?.project?.project_name || projectId }}
          </p>
          <div class="mt-0.5 flex items-center gap-2">
            <div class="h-1.5 w-28 overflow-hidden rounded-full bg-gray-200">
              <div
                class="h-full rounded-full transition-all"
                :class="percent >= 100 ? 'bg-green-500' : 'bg-indigo-500'"
                :style="{ width: Math.min(percent, 100) + '%' }"
              ></div>
            </div>
            <span class="text-[11px] font-medium text-gray-500">{{ Math.round(percent) }}%</span>
          </div>
        </div>
      </div>
    </AppHeader>

    <div class="flex items-center gap-2 border-b border-gray-200 bg-white px-4 py-2 sm:px-6">
      <input
        v-model="searchText"
        type="text"
        placeholder="Search tasks…"
        class="w-48 rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
      />
      <select
        v-model="filterSme"
        class="rounded-md border-gray-300 text-sm text-gray-700 focus:border-indigo-500 focus:ring-indigo-500"
      >
        <option value="">All SMEs</option>
        <option v-for="sme in smeOptions" :key="sme.value" :value="sme.value">{{ sme.label }}</option>
      </select>
      <select
        v-model="filterPriority"
        class="rounded-md border-gray-300 text-sm text-gray-700 focus:border-indigo-500 focus:ring-indigo-500"
      >
        <option value="">All priorities</option>
        <option v-for="priority in PRIORITIES" :key="priority" :value="priority">{{ priority }}</option>
      </select>
      <button
        v-if="searchText || filterSme || filterPriority"
        class="text-xs text-gray-500 underline hover:text-gray-700"
        @click="clearFilters"
      >
        Clear
      </button>
      <span class="flex-1"></span>
      <Button variant="subtle" size="sm" :loading="board.loading" @click="board.reload()">
        Refresh
      </Button>
      <Button variant="solid" size="sm" @click="showNewTask = true">New Task</Button>
    </div>

    <main class="flex-1 overflow-x-auto overflow-y-hidden bg-gray-50">
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
          @open-task="openTask"
          @quick-add="quickAdd"
        />
      </div>
    </main>

    <TaskDetailModal
      v-model="showDetail"
      :task-name="selectedTask"
      @task-updated="board.reload()"
      @progress="onProgress"
    />

    <NewTaskDialog
      v-model="showNewTask"
      :project="projectId"
      @created="onTaskCreated"
    />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Button, createResource } from 'frappe-ui'
import AppHeader from '@/components/AppHeader.vue'
import KanbanColumn from '@/components/KanbanColumn.vue'
import TaskDetailModal from '@/components/TaskDetailModal.vue'
import NewTaskDialog from '@/components/NewTaskDialog.vue'
import { PRIORITIES } from '@/utils/statuses'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  projectId: { type: String, required: true },
})

const columns = ref([])

const board = createResource({
  url: 'agile_projects.api.get_board',
  makeParams: () => ({ project: props.projectId }),
  auto: true,
  onSuccess(data) {
    columns.value = data.columns.map((column) => ({
      status: column.status,
      tasks: [...column.tasks],
    }))
  },
  onError(err) {
    toast({ title: 'Failed to load board', text: errorMessage(err), type: 'error' })
  },
})

watch(
  () => props.projectId,
  () => board.reload()
)

const percent = computed(() => board.data?.project?.percent_complete || 0)

// ---- filters ----
const searchText = ref('')
const filterSme = ref('')
const filterPriority = ref('')

const smeOptions = computed(() => {
  const seen = new Map()
  for (const column of columns.value) {
    for (const task of column.tasks) {
      if (task.sme_responsible && !seen.has(task.sme_responsible)) {
        seen.set(task.sme_responsible, task.sme_name || task.sme_responsible)
      }
    }
  }
  return [...seen.entries()].map(([value, label]) => ({ value, label }))
})

function matchesFilters(task) {
  if (filterSme.value && task.sme_responsible !== filterSme.value) return false
  if (filterPriority.value && task.priority !== filterPriority.value) return false
  if (searchText.value) {
    const needle = searchText.value.toLowerCase()
    if (
      !(task.subject || '').toLowerCase().includes(needle) &&
      !(task.name || '').toLowerCase().includes(needle)
    ) {
      return false
    }
  }
  return true
}

function clearFilters() {
  searchText.value = ''
  filterSme.value = ''
  filterPriority.value = ''
}

// ---- drag & drop ----
const updateStatus = createResource({ url: 'agile_projects.api.update_task_status' })

function onCardMoved(evt, status) {
  if (!evt.added) return
  const task = evt.added.element
  const previousStatus = task.status
  task.status = status
  updateStatus
    .submit({ task: task.name, status })
    .then((data) => {
      if (board.data?.project && data.percent_complete != null) {
        board.data.project.percent_complete = data.percent_complete
      }
      // Reload to refresh blocked flags of dependent cards.
      board.reload()
    })
    .catch((err) => {
      task.status = previousStatus
      toast({ title: 'Move rejected', text: errorMessage(err), type: 'error', timeout: 8000 })
      board.reload()
    })
}

// ---- task creation ----
const createTask = createResource({ url: 'agile_projects.api.create_task' })

function quickAdd(status, subject) {
  createTask
    .submit({ project: props.projectId, subject, status })
    .then(() => {
      toast({ title: 'Task created', type: 'success', timeout: 2500 })
      board.reload()
    })
    .catch((err) => {
      toast({ title: 'Could not create task', text: errorMessage(err), type: 'error' })
    })
}

const showNewTask = ref(false)

function onTaskCreated() {
  showNewTask.value = false
  board.reload()
}

// ---- task detail drawer ----
const showDetail = ref(false)
const selectedTask = ref(null)

function openTask(task) {
  selectedTask.value = task.name
  showDetail.value = true
}

function onProgress(value) {
  if (board.data?.project && value != null) {
    board.data.project.percent_complete = value
  }
}
</script>
