<template>
  <div class="flex h-full flex-col">
    <AppHeader>
      <div class="flex min-w-0 items-center gap-3">
        <router-link to="/" class="shrink-0 text-sm text-gray-500 hover:text-gray-800">←</router-link>
        <div class="min-w-0">
          <p class="truncate text-sm font-semibold text-gray-900">
            {{ meta.data?.project_name || projectId }}
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

    <!-- toolbar -->
    <div class="border-b border-gray-200 bg-white px-4 py-2 sm:px-6">
      <div class="flex flex-wrap items-center gap-2">
        <ViewSwitcher :model-value="view" @update:model-value="changeView" />
        <span class="hidden h-5 w-px bg-gray-200 sm:block"></span>
        <FilterBar v-model="filters" />
        <span class="flex-1"></span>
        <SavedViews
          :project="projectId"
          :view-type="view"
          :filters="filters"
          @apply="applySavedView"
        />
        <Button variant="subtle" size="sm" @click="refresh">Refresh</Button>
        <Button variant="solid" size="sm" @click="showNewTask = true">New Task</Button>
      </div>
    </div>

    <!-- active view -->
    <main class="min-h-0 flex-1 overflow-hidden bg-gray-50">
      <BoardView
        v-if="view === 'board'"
        ref="activeView"
        :project="projectId"
        :filters="filters"
        @open-task="openTask"
        @progress="onProgress"
      />
      <TaskListView
        v-else-if="view === 'list'"
        ref="activeView"
        :project="projectId"
        :filters="filters"
        @open-task="openTask"
        @changed="onProgressRefresh"
      />
      <TaskTableView
        v-else-if="view === 'table'"
        ref="activeView"
        :project="projectId"
        :filters="filters"
        @open-task="openTask"
        @changed="onProgressRefresh"
      />
      <TimelineView
        v-else-if="view === 'timeline'"
        ref="activeView"
        :project="projectId"
        :filters="filters"
        @open-task="openTask"
        @changed="onProgressRefresh"
      />
      <CalendarView
        v-else-if="view === 'calendar'"
        ref="activeView"
        :project="projectId"
        :filters="filters"
        @open-task="openTask"
        @changed="onProgressRefresh"
      />
    </main>

    <TaskDetailModal
      v-model="showDetail"
      :task-name="selectedTask"
      @task-updated="onProgressRefresh"
      @progress="onProgress"
    />

    <NewTaskDialog v-model="showNewTask" :project="projectId" @created="onTaskCreated" />
  </div>
</template>

<script setup>
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Button, createResource } from 'frappe-ui'
import AppHeader from '@/components/AppHeader.vue'
import ViewSwitcher from '@/components/ViewSwitcher.vue'
import FilterBar from '@/components/FilterBar.vue'
import SavedViews from '@/components/SavedViews.vue'
import NewTaskDialog from '@/components/NewTaskDialog.vue'

// The drawer embeds the rich-text editor (Tiptap), which is large — load it
// on first use instead of blocking the board's first paint.
const TaskDetailModal = defineAsyncComponent(() =>
  import('@/components/TaskDetailModal.vue')
)
import BoardView from '@/views/BoardView.vue'
import TaskListView from '@/views/TaskListView.vue'
import TaskTableView from '@/views/TaskTableView.vue'
import TimelineView from '@/views/TimelineView.vue'
import CalendarView from '@/views/CalendarView.vue'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  projectId: { type: String, required: true },
  view: { type: String, default: 'board' },
})

const router = useRouter()

const filters = ref({})
const activeView = ref(null)
const showDetail = ref(false)
const showNewTask = ref(false)
const selectedTask = ref(null)

const meta = createResource({
  url: 'agile_projects.views.get_project_meta',
  makeParams: () => ({ project: props.projectId }),
  auto: true,
  onError(err) {
    toast({ title: 'Failed to load project', text: errorMessage(err), type: 'error' })
  },
})

watch(
  () => props.projectId,
  () => {
    filters.value = {}
    meta.reload()
  }
)

const percent = computed(() => meta.data?.percent_complete || 0)

function changeView(next) {
  router.push({ name: 'ProjectDetail', params: { projectId: props.projectId, view: next } })
}

function applySavedView(saved) {
  filters.value = saved.filters || {}
  if (saved.view_type && saved.view_type !== props.view) {
    changeView(saved.view_type)
  }
}

function refresh() {
  meta.reload()
  activeView.value?.reload?.()
}

function openTask(task) {
  selectedTask.value = typeof task === 'string' ? task : task.name
  showDetail.value = true
}

function onProgress(value) {
  if (meta.data && value != null) {
    meta.data.percent_complete = value
  }
}

function onProgressRefresh() {
  meta.reload()
  activeView.value?.reload?.()
}

function onTaskCreated() {
  showNewTask.value = false
  onProgressRefresh()
}
</script>
