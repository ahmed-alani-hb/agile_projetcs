<template>
  <div class="flex h-full flex-col">
    <div class="flex flex-wrap items-center gap-2 border-b border-gray-200 bg-white px-4 py-1.5 sm:px-6">
      <div class="flex items-center gap-0.5 rounded-md bg-gray-100 p-0.5">
        <button
          v-for="mode in VIEW_MODES"
          :key="mode"
          class="rounded px-2 py-0.5 text-xs font-medium"
          :class="viewMode === mode ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500'"
          @click="setViewMode(mode)"
        >
          {{ mode }}
        </button>
      </div>
      <span class="flex items-center gap-1.5 text-xs text-gray-500">
        <span class="inline-block h-2 w-4 rounded-sm bg-red-500"></span>
        Critical path ({{ timeline.data?.critical_path?.length || 0 }})
      </span>
      <span class="flex-1"></span>
      <span class="text-xs text-gray-400">Drag a bar to reschedule · hover for details</span>
    </div>

    <div class="min-h-0 flex-1 overflow-auto p-4">
      <div v-if="timeline.loading && !scheduled.length" class="py-16 text-center text-sm text-gray-500">
        Loading timeline…
      </div>
      <p v-else-if="!scheduled.length" class="py-16 text-center text-sm text-gray-400">
        No tasks have both a start and a due date yet. Set dates on a task to place it on the
        timeline.
      </p>
      <div v-show="scheduled.length" ref="container" class="agile-gantt"></div>
    </div>

    <div
      v-if="undated.length"
      class="max-h-32 shrink-0 overflow-y-auto border-t border-gray-200 bg-white px-4 py-2 sm:px-6"
    >
      <p class="mb-1 text-xs font-medium text-gray-500">
        {{ undated.length }} task{{ undated.length === 1 ? '' : 's' }} without dates — not shown above
      </p>
      <div class="flex flex-wrap gap-1.5">
        <button
          v-for="task in undated"
          :key="task.name"
          class="rounded-full border border-gray-200 px-2 py-0.5 text-[11px] text-gray-600 hover:border-indigo-300 hover:text-indigo-700"
          @click="$emit('open-task', task)"
        >
          {{ task.subject }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { createResource } from 'frappe-ui'
import Gantt from 'frappe-gantt'
import 'frappe-gantt-css'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  project: { type: String, required: true },
  filters: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['open-task', 'changed'])

const VIEW_MODES = ['Day', 'Week', 'Month', 'Year']
const viewMode = ref('Week')
const container = ref(null)
let gantt = null
// frappe-gantt fires on_click at the end of a drag as well as on a real click
let suppressClickUntil = 0

const timeline = createResource({
  url: 'agile_projects.views.get_timeline',
  makeParams: () => ({ project: props.project, filters: props.filters }),
  auto: true,
  onSuccess() {
    nextTick(render)
  },
  onError(err) {
    toast({ title: 'Failed to load timeline', text: errorMessage(err), type: 'error' })
  },
})

watch(
  () => [props.project, props.filters],
  () => timeline.reload(),
  { deep: true }
)

const allTasks = computed(() => timeline.data?.tasks || [])
const scheduled = computed(() =>
  allTasks.value.filter((t) => t.exp_start_date && t.exp_end_date)
)
const undated = computed(() => allTasks.value.filter((t) => !t.exp_start_date || !t.exp_end_date))

const byName = computed(() => {
  const map = {}
  for (const task of allTasks.value) map[task.name] = task
  return map
})

function statusClass(status) {
  return 'gantt-status-' + String(status || '').replace(/[^a-z]/gi, '').toLowerCase()
}

function ganttTasks() {
  const visible = new Set(scheduled.value.map((t) => t.name))
  return scheduled.value.map((task) => ({
    id: task.name,
    name: task.subject,
    start: task.exp_start_date,
    end: task.exp_end_date,
    progress: Number(task.progress) || 0,
    // only link to predecessors that are actually drawn
    dependencies: (task.depends_on || []).filter((d) => visible.has(d)).join(','),
    // MUST be a single token: the library passes this straight to
    // DOMTokenList.add(), which throws InvalidCharacterError on whitespace.
    custom_class: statusClass(task.status),
  }))
}

// Extra state classes are applied by us, because classList.add() accepts
// several separate tokens but not one token containing spaces.
function applyStateClasses() {
  if (!gantt || !gantt.bars) return
  for (const bar of gantt.bars) {
    const task = byName.value[bar.task?.id]
    if (!task || !bar.group) continue
    const extra = []
    if (task.is_critical) extra.push('gantt-critical')
    if (task.is_blocked) extra.push('gantt-blocked')
    if (extra.length) bar.group.classList.add(...extra)
  }
}

function render() {
  if (!container.value || !scheduled.value.length) return
  container.value.innerHTML = ''
  try {
    gantt = new Gantt(container.value, ganttTasks(), {
      view_mode: viewMode.value,
      infinite_padding: false,
      readonly_progress: true,
      // dragging a bar must not silently rewrite every downstream task
      move_dependencies: false,
      today_button: true,
      popup_on: 'hover',
      bar_height: 26,
      padding: 16,
      popup: (ctx) => {
        const task = byName.value[ctx.task.id]
        // returning false suppresses the popup (and avoids showing the
        // previously hovered task's title)
        if (!task) return false
        // textContent, not set_title/set_subtitle — those assign innerHTML and
        // the subject is user-supplied
        ctx.get_title().textContent = task.subject
        ctx.get_subtitle().textContent =
          `${task.status}${task.complexity_points ? ' · ' + task.complexity_points + ' pts' : ''}` +
          (task.is_critical ? ' · on critical path' : '')
      },
      on_click: (task) => {
        if (Date.now() < suppressClickUntil) return
        const match = byName.value[task.id]
        if (match) emit('open-task', match)
      },
      on_date_change: (task, start, end) => {
        suppressClickUntil = Date.now() + 400
        persistDates(task.id, start, end)
      },
    })
    applyStateClasses()
  } catch (err) {
    gantt = null
    console.error('Gantt render failed', err)
    toast({
      title: 'Could not render the timeline',
      text: String(err?.message || err),
      type: 'error',
    })
  }
}

function setViewMode(mode) {
  viewMode.value = mode
  if (!gantt) {
    // also recovers if a previous render threw
    render()
    return
  }
  gantt.change_view_mode(mode)
  // change_view_mode rebuilds every Bar, dropping our extra classes
  applyStateClasses()
}

// Local date parts — toISOString() would shift the day for users west of UTC.
function toDateStr(value) {
  const date = value instanceof Date ? value : new Date(value)
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

const updateDates = createResource({ url: 'agile_projects.views.update_task_dates' })

function persistDates(taskName, start, end) {
  const startStr = toDateStr(start)
  const endStr = toDateStr(end)
  updateDates
    .submit({ task: taskName, exp_start_date: startStr, exp_end_date: endStr })
    .then(() => {
      // Update in place rather than reloading: a reload would rebuild the
      // chart and throw away the user's scroll position. move_dependencies is
      // off, so only this task changed.
      const task = byName.value[taskName]
      if (task) {
        task.exp_start_date = startStr
        task.exp_end_date = endStr
      }
      emit('changed')
    })
    .catch((err) => {
      toast({ title: 'Could not reschedule', text: errorMessage(err), type: 'error' })
      timeline.reload()
    })
}

onBeforeUnmount(() => {
  gantt = null
  if (container.value) container.value.innerHTML = ''
})

defineExpose({ reload: () => timeline.reload() })
</script>

<style>
.agile-gantt .gantt-critical .bar {
  fill: #ef4444;
}
.agile-gantt .gantt-critical .bar-progress {
  fill: #b91c1c;
}
.agile-gantt .gantt-blocked .bar {
  stroke: #dc2626;
  stroke-width: 2;
}
.agile-gantt .gantt-status-done .bar-progress {
  fill: #22c55e;
}
</style>
