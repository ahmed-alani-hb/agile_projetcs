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
        <span class="inline-block h-2 w-4 rounded-sm" :style="{ background: ACCENT_MUTED }"></span>
        Module to go-live
      </span>
      <span class="flex items-center gap-1.5 text-xs text-gray-500">
        <span class="inline-block h-2 w-4 rounded-sm bg-gray-700"></span>
        Cutover step
      </span>
      <span v-if="inferredCount" class="text-xs text-amber-600" :title="inferredTitle">
        ⚠ {{ inferredCount }} inferred start{{ inferredCount === 1 ? '' : 's' }}
      </span>
      <span class="flex-1"></span>
    </div>

    <div class="min-h-0 flex-1 overflow-auto p-4">
      <div v-if="roadmap.loading && !bars.length" class="py-16 text-center text-sm text-gray-500">
        Loading roadmap…
      </div>
      <p v-else-if="!bars.length" class="py-16 text-center text-sm text-gray-400">
        Nothing to plot yet. A module needs a target go-live, and a cutover step needs planned
        dates, before either can appear here.
      </p>
      <div v-show="bars.length" ref="container" class="agile-roadmap"></div>
    </div>

    <p class="shrink-0 border-t border-gray-200 bg-white px-4 py-2 text-[11px] text-gray-400 sm:px-6">
      A module has no start date of its own, so its bar begins at the earliest start among its
      tasks — or the project's start, flagged above, when it has none.
    </p>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import Gantt from 'frappe-gantt'
import 'frappe-gantt-css'
import { createResource } from 'frappe-ui'
import { ACCENT_MUTED } from '@/utils/charts'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  project: { type: String, required: true },
})

const VIEW_MODES = ['Week', 'Month', 'Year']
const viewMode = ref('Month')
const container = ref(null)
let gantt = null

const roadmap = createResource({
  url: 'agile_projects.modules.get_roadmap',
  makeParams: () => ({ project: props.project }),
  auto: true,
  onSuccess() {
    nextTick(render)
  },
  onError(err) {
    toast({ title: 'Failed to load roadmap', text: errorMessage(err), type: 'error' })
  },
})

watch(
  () => props.project,
  () => roadmap.reload()
)

const bars = computed(() => [
  ...(roadmap.data?.modules || []),
  ...(roadmap.data?.cutover || []),
])

const byId = computed(() => {
  const map = {}
  for (const bar of bars.value) map[bar.id] = bar
  return map
})

const inferredCount = computed(
  () => (roadmap.data?.modules || []).filter((m) => m.start_is_inferred).length
)
const inferredTitle = computed(
  () =>
    'These modules have no dated tasks, so their bar starts at the project start rather than ' +
    'at real work.'
)

function classFor(bar) {
  // Single token: the library hands this straight to DOMTokenList.add(),
  // which throws on whitespace.
  if (bar.kind === 'cutover') {
    return 'roadmap-cutover-' + String(bar.status || '').replace(/[^a-z]/gi, '').toLowerCase()
  }
  return 'roadmap-gate-' + String(bar.gate || '').replace(/[^a-z]/gi, '').toLowerCase()
}

function ganttTasks() {
  const present = new Set(bars.value.map((b) => b.id))
  return bars.value.map((bar) => ({
    id: bar.id,
    name: bar.label,
    start: bar.start,
    end: bar.end,
    progress: 0,
    dependencies: bar.depends_on && present.has(bar.depends_on) ? bar.depends_on : '',
    custom_class: classFor(bar),
  }))
}

// Actual vs planned for cutover steps, drawn after render: the library assigns
// exactly one row per bar, so a second bar per row is not expressible.
function drawActuals() {
  if (!gantt || !gantt.bars) return
  for (const ganttBar of gantt.bars) {
    const bar = byId.value[ganttBar.task?.id]
    if (!bar || !ganttBar.group) continue
    const existing = ganttBar.group.querySelector('.roadmap-actual')
    if (existing) existing.remove()
    if (bar.kind !== 'cutover' || !bar.actual_start || !bar.actual_end) continue
    try {
      const rect = ganttBar.group.querySelector('.bar')
      if (!rect) continue
      const x = Number(rect.getAttribute('x'))
      const width = Number(rect.getAttribute('width'))
      const y = Number(rect.getAttribute('y'))
      const height = Number(rect.getAttribute('height'))
      if (![x, width, y, height].every(Number.isFinite)) continue

      const pStart = new Date(bar.start).getTime()
      const pEnd = new Date(bar.end).getTime()
      const span = pEnd - pStart
      if (!(span > 0)) continue
      const clamp = (v) => Math.max(0, Math.min(1, v))
      const left = clamp((new Date(bar.actual_start).getTime() - pStart) / span)
      const right = clamp((new Date(bar.actual_end).getTime() - pStart) / span)

      const actual = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
      actual.setAttribute('class', 'roadmap-actual')
      actual.setAttribute('x', String(x + left * width))
      actual.setAttribute('width', String(Math.max((right - left) * width, 2)))
      actual.setAttribute('y', String(y + height - 5))
      actual.setAttribute('height', '3')
      actual.setAttribute('rx', '1.5')
      ganttBar.group.appendChild(actual)
    } catch (err) {
      // Decoration only; never take the chart down for it.
    }
  }
}

function render() {
  if (!container.value || !bars.value.length) return
  container.value.innerHTML = ''
  try {
    gantt = new Gantt(container.value, ganttTasks(), {
      view_mode: viewMode.value,
      infinite_padding: false,
      readonly: true,
      today_button: true,
      popup_on: 'hover',
      bar_height: 24,
      padding: 16,
      popup: (ctx) => {
        const bar = byId.value[ctx.task.id]
        if (!bar) return false
        // textContent, not set_title: these are user-supplied strings.
        ctx.get_title().textContent = bar.label
        const parts = []
        if (bar.kind === 'module') {
          parts.push(`Gate ${bar.gate}`, `go-live ${bar.end}`)
          if (bar.start_is_inferred) parts.push('start inferred')
        } else {
          parts.push(bar.status)
          if (bar.actual_start) parts.push(`actual ${bar.actual_start} → ${bar.actual_end || '…'}`)
        }
        ctx.get_subtitle().textContent = parts.join(' · ')
      },
    })
    drawActuals()
  } catch (err) {
    gantt = null
    toast({ title: 'Could not render the roadmap', text: String(err?.message || err), type: 'error' })
  }
}

function setViewMode(mode) {
  viewMode.value = mode
  if (!gantt) {
    render()
    return
  }
  gantt.change_view_mode(mode)
  // change_view_mode rebuilds every bar, dropping our overlays.
  drawActuals()
}

onBeforeUnmount(() => {
  gantt = null
  if (container.value) container.value.innerHTML = ''
})

defineExpose({ reload: () => roadmap.reload() })
</script>

<style>
/* Gates: the same sequential reading as the gate board, light to dark. */
.agile-roadmap .roadmap-gate-configure .bar {
  fill: #e0e7ff;
}
.agile-roadmap .roadmap-gate-migrate .bar {
  fill: #c7d2fe;
}
.agile-roadmap .roadmap-gate-uat .bar {
  fill: #a5b4fc;
}
.agile-roadmap .roadmap-gate-signoff .bar {
  fill: #818cf8;
}
.agile-roadmap .roadmap-gate-live .bar {
  fill: #4338ca;
}

/* Cutover steps read as a distinct family: darker, and failure is the one
   place a status colour is warranted. */
.agile-roadmap [class*='roadmap-cutover-'] .bar {
  fill: #6b7280;
}
.agile-roadmap .roadmap-cutover-done .bar {
  fill: #374151;
}
.agile-roadmap .roadmap-cutover-failed .bar {
  fill: #dc2626;
}
.agile-roadmap .roadmap-cutover-skipped .bar {
  fill: #d1d5db;
}
.agile-roadmap .roadmap-actual {
  fill: #111827;
  opacity: 0.85;
}
</style>
