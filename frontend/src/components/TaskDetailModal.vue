<template>
  <teleport to="body">
    <transition name="fade">
      <div v-if="modelValue" class="fixed inset-0 z-40 bg-black/30" @click="close"></div>
    </transition>
    <transition name="slide">
      <div
        v-if="modelValue"
        class="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col bg-white shadow-2xl"
      >
        <!-- header -->
        <div class="flex items-center gap-3 border-b border-gray-200 px-5 py-3">
          <span class="truncate font-mono text-xs text-gray-400">{{ taskName }}</span>
          <select
            v-if="detail.data"
            :value="detail.data.status"
            class="rounded-md border-gray-300 py-1 text-sm font-medium focus:border-indigo-500 focus:ring-indigo-500"
            :disabled="statusResource.loading"
            @change="changeStatus($event.target.value)"
          >
            <option v-for="status in STATUSES" :key="status" :value="status">{{ status }}</option>
          </select>
          <span
            v-if="detail.data"
            class="rounded-full px-2 py-0.5 text-[11px] font-medium"
            :class="statusMeta.pill"
          >
            {{ detail.data.status }}
          </span>
          <span class="flex-1"></span>
          <button class="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700" @click="close">
            ✕
          </button>
        </div>

        <!-- blocked alert -->
        <div
          v-if="detail.data?.is_blocked"
          class="flex items-start gap-2 border-b border-red-100 bg-red-50 px-5 py-2.5 text-sm text-red-800"
        >
          <span>⛔</span>
          <div>
            <p class="font-medium">This task is blocked</p>
            <p class="text-xs">
              {{ openBlockers.length }} dependenc{{ openBlockers.length === 1 ? 'y is' : 'ies are' }}
              not Done yet. It cannot move to In Progress or Done.
            </p>
          </div>
        </div>

        <!-- tabs -->
        <div class="flex gap-1 border-b border-gray-200 px-5 pt-2">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            class="rounded-t-md px-3 py-2 text-sm font-medium"
            :class="
              activeTab === tab.key
                ? 'border-b-2 border-indigo-600 text-indigo-700'
                : 'text-gray-500 hover:text-gray-800'
            "
            @click="activeTab = tab.key"
          >
            {{ tab.label }}
          </button>
        </div>

        <!-- body -->
        <div class="thin-scrollbar flex-1 overflow-y-auto px-5 py-4">
          <div v-if="detail.loading && !detail.data" class="py-10 text-center text-sm text-gray-500">
            Loading task…
          </div>

          <template v-else-if="detail.data">
            <!-- DETAILS TAB -->
            <div v-show="activeTab === 'details'" class="space-y-5">
              <div>
                <label class="text-xs font-medium text-gray-500">Subject</label>
                <input
                  v-model="form.subject"
                  type="text"
                  class="mt-1 w-full rounded-md border-gray-300 text-sm font-medium focus:border-indigo-500 focus:ring-indigo-500"
                  @change="saveField('subject', form.subject)"
                />
              </div>

              <div>
                <label class="text-xs font-medium text-gray-500">Description</label>
                <div
                  class="mt-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus-within:border-indigo-500 focus-within:ring-1 focus-within:ring-indigo-500"
                >
                  <TextEditor
                    :content="form.description"
                    :editable="true"
                    placeholder="Add a description…"
                    editor-class="prose-sm max-w-none min-h-[70px] focus:outline-none"
                    @change="(html) => (form.description = html)"
                    @blur="saveDescription"
                  />
                </div>
              </div>

              <div class="grid grid-cols-2 gap-4">
                <div>
                  <label class="text-xs font-medium text-gray-500">Complexity Points</label>
                  <select
                    v-model="form.complexity_points"
                    class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                    @change="saveField('complexity_points', form.complexity_points)"
                  >
                    <option value="">Unestimated</option>
                    <option v-for="points in POINT_OPTIONS" :key="points" :value="points">
                      {{ points }} points
                    </option>
                  </select>
                </div>
                <div>
                  <label class="text-xs font-medium text-gray-500">Priority</label>
                  <select
                    v-model="form.priority"
                    class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                    @change="saveField('priority', form.priority)"
                  >
                    <option v-for="priority in PRIORITIES" :key="priority" :value="priority">
                      {{ priority }}
                    </option>
                  </select>
                </div>
                <div>
                  <label class="text-xs font-medium text-gray-500">SME Responsible</label>
                  <div class="mt-1">
                    <EmployeePicker
                      :model-value="form.sme_responsible"
                      @update:model-value="(value) => saveField('sme_responsible', value)"
                    />
                  </div>
                </div>
                <div>
                  <label class="text-xs font-medium text-gray-500">Progress</label>
                  <div class="mt-2 flex items-center gap-2">
                    <input
                      v-model.number="form.progress"
                      type="range"
                      min="0"
                      max="100"
                      step="5"
                      class="w-full accent-indigo-600"
                      :disabled="detail.data.status === 'Done'"
                      @change="saveField('progress', form.progress)"
                    />
                    <span class="w-10 text-right text-xs font-medium text-gray-600">
                      {{ form.progress || 0 }}%
                    </span>
                  </div>
                </div>
                <div>
                  <label class="text-xs font-medium text-gray-500">Start Date</label>
                  <input
                    v-model="form.exp_start_date"
                    type="date"
                    class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                    @change="saveField('exp_start_date', form.exp_start_date)"
                  />
                </div>
                <div>
                  <label class="text-xs font-medium text-gray-500">Due Date</label>
                  <input
                    v-model="form.exp_end_date"
                    type="date"
                    class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                    @change="saveField('exp_end_date', form.exp_end_date)"
                  />
                </div>
              </div>

              <!-- dependencies / blockers (editable — stock ERPNext's Gantt is read-only) -->
              <div>
                <p class="text-xs font-medium text-gray-500">
                  Dependencies ({{ detail.data.depends_on.length }})
                </p>
                <p v-if="!detail.data.depends_on.length" class="mt-1 text-sm text-gray-400">
                  No dependencies yet. This task can start at any time.
                </p>
                <ul v-else class="mt-2 space-y-1.5">
                  <li
                    v-for="dep in detail.data.depends_on"
                    :key="dep.name"
                    class="flex items-center gap-2 rounded-md border border-gray-200 px-3 py-2"
                  >
                    <span>{{ dep.status === 'Done' ? '✅' : '⛔' }}</span>
                    <span class="font-mono text-[11px] text-gray-400">{{ dep.name }}</span>
                    <span class="min-w-0 flex-1 truncate text-sm text-gray-800">{{ dep.subject }}</span>
                    <span
                      class="rounded-full px-2 py-0.5 text-[11px] font-medium"
                      :class="(STATUS_META[dep.status] || STATUS_META.Backlog).pill"
                    >
                      {{ dep.status }}
                    </span>
                    <button
                      class="text-xs text-gray-400 hover:text-red-600"
                      title="Remove dependency"
                      :disabled="dependencyResource.loading"
                      @click="removeDependency(dep.name)"
                    >
                      ✕
                    </button>
                  </li>
                </ul>

                <select
                  class="mt-2 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                  :value="''"
                  :disabled="dependencyResource.loading"
                  @change="addDependency($event.target.value), ($event.target.value = '')"
                >
                  <option value="" disabled>+ Add a dependency…</option>
                  <option v-for="option in dependencyOptions" :key="option.name" :value="option.name">
                    {{ option.subject }} ({{ option.status }})
                  </option>
                </select>
                <p class="mt-1 text-[11px] text-gray-400">
                  This task cannot move to In Progress or Done until every dependency is Done.
                </p>
              </div>

              <!-- meta -->
              <div class="grid grid-cols-2 gap-2 border-t border-gray-100 pt-3 text-xs text-gray-500">
                <p>Owner: {{ detail.data.owner }}</p>
                <p>Hours logged: {{ formatHours(detail.data.total_hours) }}</p>
                <p v-if="detail.data.completed_on">Completed on: {{ detail.data.completed_on }}</p>
                <p v-if="detail.data.completed_by">Completed by: {{ detail.data.completed_by }}</p>
              </div>
            </div>

            <!-- CHECKLIST TAB -->
            <div v-show="activeTab === 'checklist'">
              <ChecklistSection
                v-if="detail.data.project"
                :project="detail.data.project"
                @progress="(value) => emit('progress', value)"
              />
              <p v-else class="py-10 text-center text-sm text-gray-500">
                This task is not linked to a Project, so there is no ERP readiness checklist.
              </p>
            </div>

            <!-- TIME TAB -->
            <div v-show="activeTab === 'time'">
              <TimesheetSection :task="taskName" @logged="onTimeLogged" />
            </div>
          </template>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { TextEditor, createResource } from 'frappe-ui'
import EmployeePicker from './EmployeePicker.vue'
import ChecklistSection from './ChecklistSection.vue'
import TimesheetSection from './TimesheetSection.vue'
import { STATUSES, STATUS_META, POINT_OPTIONS, PRIORITIES } from '@/utils/statuses'
import { formatHours, toDateInput } from '@/utils/format'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  taskName: { type: String, default: null },
})

const emit = defineEmits(['update:modelValue', 'task-updated', 'progress'])

const tabs = [
  { key: 'details', label: 'Details' },
  { key: 'checklist', label: 'ERP Checklist' },
  { key: 'time', label: 'Time' },
]

const activeTab = ref('details')

const form = reactive({
  subject: '',
  description: '',
  priority: '',
  complexity_points: '',
  sme_responsible: null,
  exp_start_date: '',
  exp_end_date: '',
  progress: 0,
})

const detail = createResource({
  url: 'agile_projects.api.get_task',
  onSuccess(data) {
    form.subject = data.subject || ''
    // Task.description is a Text Editor (HTML) field; the editor round-trips it
    form.description = data.description || ''
    form.priority = data.priority || 'Medium'
    form.complexity_points = data.complexity_points || ''
    form.sme_responsible = data.sme_responsible || null
    // date inputs need YYYY-MM-DD; v16 returns a datetime
    form.exp_start_date = toDateInput(data.exp_start_date)
    form.exp_end_date = toDateInput(data.exp_end_date)
    form.progress = data.progress || 0
  },
  onError(err) {
    toast({ title: 'Failed to load task', text: errorMessage(err), type: 'error' })
  },
})

watch(
  () => [props.modelValue, props.taskName],
  ([open, name]) => {
    if (open && name) {
      activeTab.value = 'details'
      // drop the previous task's data first, otherwise the drawer renders the
      // old task while the new one loads and a save in that window would write
      // the old values onto the new task
      if (detail.data?.name !== name) {
        detail.data = null
      }
      detail.submit({ task: name })
    }
  },
  { immediate: true }
)

const statusMeta = computed(
  () => STATUS_META[detail.data?.status] || STATUS_META.Backlog
)

const openBlockers = computed(() =>
  (detail.data?.depends_on || []).filter((dep) => dep.status !== 'Done')
)

function close() {
  emit('update:modelValue', false)
}

// ---- saves ----
const updateTask = createResource({ url: 'agile_projects.api.update_task' })

function saveField(field, value) {
  updateTask
    .submit({ task: props.taskName, fields: { [field]: value ?? '' } })
    .then((data) => {
      detail.data = data
      emit('task-updated')
    })
    .catch((err) => {
      toast({ title: 'Could not save', text: errorMessage(err), type: 'error' })
      detail.submit({ task: props.taskName })
    })
}

const statusResource = createResource({ url: 'agile_projects.api.update_task_status' })

function changeStatus(status) {
  statusResource
    .submit({ task: props.taskName, status })
    .then((data) => {
      if (data.percent_complete != null) emit('progress', data.percent_complete)
      detail.submit({ task: props.taskName })
      emit('task-updated')
    })
    .catch((err) => {
      toast({ title: 'Status change rejected', text: errorMessage(err), type: 'error', timeout: 8000 })
      detail.submit({ task: props.taskName })
    })
}

function saveDescription() {
  if ((detail.data?.description || '') === (form.description || '')) return
  saveField('description', form.description)
}

function onTimeLogged() {
  detail.submit({ task: props.taskName })
  emit('task-updated')
}

// ---- dependencies (add/remove; stock ERPNext offers no UI for this outside
// the Desk form's child table) ----
const dependencyResource = createResource({ url: 'agile_projects.views.set_task_dependency' })
const removeResource = createResource({ url: 'agile_projects.views.remove_task_dependency' })

const candidates = createResource({
  url: 'agile_projects.views.get_tasks_list',
  makeParams: () => ({
    project: detail.data?.project,
    order_by: 'subject asc',
    page_length: 500,
    fields: ['name', 'subject', 'status'],
  }),
})

watch(
  () => detail.data?.project,
  (project) => {
    if (project) candidates.reload()
  }
)

const dependencyOptions = computed(() => {
  const existing = new Set((detail.data?.depends_on || []).map((d) => d.name))
  return (candidates.data?.tasks || []).filter(
    (task) => task.name !== props.taskName && !existing.has(task.name)
  )
})

function addDependency(dependsOn) {
  if (!dependsOn) return
  dependencyResource
    .submit({ task: props.taskName, depends_on: dependsOn })
    .then(() => {
      toast({ title: 'Dependency added', type: 'success', timeout: 2000 })
      detail.submit({ task: props.taskName })
      emit('task-updated')
    })
    .catch((err) => {
      toast({ title: 'Could not add dependency', text: errorMessage(err), type: 'error' })
    })
}

function removeDependency(dependsOn) {
  removeResource
    .submit({ task: props.taskName, depends_on: dependsOn })
    .then(() => {
      detail.submit({ task: props.taskName })
      emit('task-updated')
    })
    .catch((err) => {
      toast({ title: 'Could not remove dependency', text: errorMessage(err), type: 'error' })
    })
}
</script>
