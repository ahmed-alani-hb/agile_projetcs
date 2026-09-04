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
      <span v-if="hasMilestones" class="flex items-center gap-1.5 text-xs text-gray-500">
        <span class="inline-block h-2 w-2 rotate-45 bg-indigo-700"></span>
        Milestone
      </span>
      <span v-if="hasActuals" class="flex items-center gap-1.5 text-xs text-gray-500">
        <span class="inline-block h-0.5 w-4 bg-gray-800"></span>
        Actual
      </span>
      <span class="flex-1"></span>
      <span class="hidden text-xs text-gray-400 lg:inline">Drag a bar to reschedule</span>
      <Button variant="subtle" size="sm" :loading="exporting" @click="exportPng">
        Export PNG
      </Button>
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
import { Button } from 'frappe-ui'
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

// Everything below is applied by us after the library renders, because
// frappe-gantt 1.2.2 has no concept of any of it: classList.add() accepts
// several tokens but not one containing spaces, there is no milestone type,
// and compute_y() assigns exactly one row per task so a second bar is not
// expressible. Each patch degrades to "the bar renders normally" if the
// library changes shape under us.
function applyStateClasses() {
  if (!gantt || !gantt.bars) return
  for (const bar of gantt.bars) {
    const task = byName.value[bar.task?.id]
    if (!task || !bar.group) continue
    // toggle, not add: a reschedule can take a task *off* the critical path,
    // and an add-only pass would leave it painted red forever.
    bar.group.classList.toggle('gantt-critical', !!task.is_critical)
    bar.group.classList.toggle('gantt-blocked', !!task.is_blocked)
    bar.group.classList.toggle('gantt-milestone', !!task.is_milestone)
    drawBaseline(bar, task)
    drawMilestone(bar, task)
  }
}

// Planned vs actual. act_start_date / act_end_date exist on every ERPNext Task
// and were fetched nowhere in this app until now.
function drawMilestone(bar, task) {
  const existing = bar.group.querySelector('.gantt-diamond')
  if (existing) existing.remove()
  if (!task.is_milestone) return
  try {
    const planned = bar.group.querySelector('.bar')
    if (!planned) return
    const x = Number(planned.getAttribute('x'))
    const y = Number(planned.getAttribute('y'))
    const height = Number(planned.getAttribute('height'))
    if (![x, y, height].every(Number.isFinite)) return
    const size = Math.min(height, 14)
    const cx = x
    const cy = y + height / 2
    const diamond = document.createElementNS('http://www.w3.org/2000/svg', 'polygon')
    diamond.setAttribute('class', 'gantt-diamond')
    diamond.setAttribute(
      'points',
      `${cx},${cy - size / 2} ${cx + size / 2},${cy} ${cx},${cy + size / 2} ${cx - size / 2},${cy}`
    )
    bar.group.appendChild(diamond)
  } catch (err) {
    // Decoration only.
  }
}

function drawBaseline(bar, task) {
  const existing = bar.group.querySelector('.gantt-actual')
  if (existing) existing.remove()
  if (!task.act_start_date || !task.act_end_date || !gantt) return

  try {
    const planned = bar.group.querySelector('.bar')
    if (!planned) return
    const x = Number(planned.getAttribute('x'))
    const width = Number(planned.getAttribute('width'))
    const y = Number(planned.getAttribute('y'))
    const height = Number(planned.getAttribute('height'))
    if (![x, width, y, height].every(Number.isFinite)) return

    // Map the actual window onto the planned bar's own pixel span, so this
    // needs no access to the library's internal date scale.
    const pStart = new Date(task.exp_start_date).getTime()
    const pEnd = new Date(task.exp_end_date).getTime()
    const span = pEnd - pStart
    if (!(span > 0)) return
    const aStart = new Date(task.act_start_date).getTime()
    const aEnd = new Date(task.act_end_date).getTime()
    if (!Number.isFinite(aStart) || !Number.isFinite(aEnd)) return

    const clamp = (value) => Math.max(0, Math.min(1, value))
    const left = clamp((aStart - pStart) / span)
    const right = clamp((aEnd - pStart) / span)

    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
    rect.setAttribute('class', 'gantt-actual')
    rect.setAttribute('x', String(x + left * width))
    rect.setAttribute('width', String(Math.max((right - left) * width, 2)))
    rect.setAttribute('y', String(y + height - 5))
    rect.setAttribute('height', '3')
    rect.setAttribute('rx', '1.5')
    bar.group.appendChild(rect)
  } catch (err) {
    // A baseline is a nicety; never let it take the chart down with it.
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
const criticalPath = createResource({ url: 'agile_projects.views.get_critical_path' })

// Rescheduling can move which tasks have zero slack. Refetch just the path
// rather than the whole timeline, so the red highlighting stays truthful
// without costing the user their scroll position.
function refreshCriticalPath() {
  criticalPath
    .submit({ project: props.project, filters: props.filters })
    .then((data) => {
      const critical = new Set(data.critical_path || [])
      for (const task of allTasks.value) task.is_critical = critical.has(task.name)
      if (timeline.data) timeline.data.critical_path = data.critical_path
      applyStateClasses()
    })
    .catch(() => {
      // Leave the previous highlighting rather than clearing it; a wrong-but-
      // stale path is less alarming than every bar suddenly turning grey.
    })
}

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
      refreshCriticalPath()
      emit('changed')
    })
    .catch((err) => {
      toast({ title: 'Could not reschedule', text: errorMessage(err), type: 'error' })
      timeline.reload()
    })
}

const hasMilestones = computed(() => scheduled.value.some((task) => task.is_milestone))
const hasActuals = computed(() =>
  scheduled.value.some((task) => task.act_start_date && task.act_end_date)
)

// The library has no export — it draws SVG. Serialising it ourselves is safe
// here only because the chart embeds no external images (the `thumbnail`
// feature is unused), so the canvas is never tainted.
const exporting = ref(false)

async function exportPng() {
  const svg = container.value?.querySelector('svg')
  if (!svg) return
  exporting.value = true
  try {
    const clone = svg.cloneNode(true)
    const width = svg.width?.baseVal?.value || svg.clientWidth || 1200
    const height = svg.height?.baseVal?.value || svg.clientHeight || 600
    clone.setAttribute('width', String(width))
    clone.setAttribute('height', String(height))
    // Inline the scoped styles: a detached SVG has no stylesheet, so without
    // this every bar exports in the library's default white.
    const style = document.createElementNS('http://www.w3.org/2000/svg', 'style')
    style.textContent = collectGanttCss()
    clone.insertBefore(style, clone.firstChild)

    const markup = new XMLSerializer().serializeToString(clone)
    const url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup)}`
    const image = new Image()
    await new Promise((resolve, reject) => {
      image.onload = resolve
      image.onerror = () => reject(new Error('Could not rasterise the chart'))
      image.src = url
    })

    const scale = window.devicePixelRatio || 1
    const canvas = document.createElement('canvas')
    canvas.width = width * scale
    canvas.height = height * scale
    const context = canvas.getContext('2d')
    context.scale(scale, scale)
    context.fillStyle = '#ffffff'
    context.fillRect(0, 0, width, height)
    context.drawImage(image, 0, 0)

    const link = document.createElement('a')
    link.download = `${props.project}-timeline.png`
    link.href = canvas.toDataURL('image/png')
    link.click()
  } catch (err) {
    toast({ title: 'Could not export', text: String(err?.message || err), type: 'error' })
  } finally {
    exporting.value = false
  }
}

function collectGanttCss() {
  const rules = []
  for (const sheet of Array.from(document.styleSheets)) {
    let list
    try {
      list = sheet.cssRules
    } catch (err) {
      // A cross-origin stylesheet throws on access; skip it.
      continue
    }
    for (const rule of Array.from(list || [])) {
      if (rule.cssText && /\.bar|\.gantt|\.arrow|\.grid|\.upper-text|\.lower-text/.test(rule.selectorText || '')) {
        rules.push(rule.cssText)
      }
    }
  }
  return rules.join('\n')
}

onBeforeUnmount(() => {
  gantt = null
  if (container.value) container.value.innerHTML = ''
})

defineExpose({ reload: () => timeline.reload() })
</script>

<style>
/* Status fills. Five gantt-status-* classes were being emitted with only
   "done" styled, so every other status rendered in the library's default
   white. These are the board's own colours so the two views agree. */
.agile-gantt .gantt-status-backlog .bar {
  fill: #e5e7eb;
}
.agile-gantt .gantt-status-todo .bar {
  fill: #bfdbfe;
}
.agile-gantt .gantt-status-inprogress .bar {
  fill: #fed7aa;
}
.agile-gantt .gantt-status-qacodereview .bar {
  fill: #e9d5ff;
}
.agile-gantt .gantt-status-blocked .bar {
  fill: #fecaca;
}
.agile-gantt .gantt-status-done .bar {
  fill: #bbf7d0;
}
.agile-gantt .gantt-status-done .bar-progress {
  fill: #22c55e;
}

/* Critical path and blockers override the status fill. */
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

/* Actual dates, drawn as a rule inside the planned bar — the library assigns
   one row per task, so a second full bar is not expressible. */
.agile-gantt .gantt-actual {
  fill: #1f2937;
  opacity: 0.75;
}

/* Milestones. The library has no milestone type and stretches a zero-duration
   bar to a full day, so the bar is hidden and a diamond drawn in its place. */
.agile-gantt .gantt-milestone .bar,
.agile-gantt .gantt-milestone .bar-progress {
  fill: transparent;
  stroke: none;
}
.agile-gantt .gantt-diamond {
  fill: #4338ca;
}
</style>
