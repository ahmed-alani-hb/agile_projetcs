<template>
  <div>
    <p v-if="!bars.length" class="py-8 text-center text-sm text-gray-500">
      No project has both a start and an end date, so there is nothing to lay out yet.
    </p>

    <div v-else>
      <!-- Month ruler -->
      <div class="relative mb-1 ml-40 h-4 border-b border-gray-200">
        <span
          v-for="tick in ticks"
          :key="tick.at"
          class="absolute -top-0 text-[10px] text-gray-400"
          :style="{ left: tick.left + '%' }"
        >
          {{ tick.label }}
        </span>
      </div>

      <div class="relative">
        <!-- Today, if it falls inside the window -->
        <div
          v-if="todayLeft !== null"
          class="pointer-events-none absolute inset-y-0 z-10 w-px bg-red-400"
          :style="{ left: `calc(10rem + ${todayLeft}% * (100% - 10rem) / 100)` }"
        >
          <span class="absolute -top-4 -translate-x-1/2 text-[10px] font-medium text-red-500">
            today
          </span>
        </div>

        <div v-for="bar in bars" :key="bar.name" class="flex items-center gap-2 py-1">
          <router-link
            class="w-40 shrink-0 truncate text-xs text-gray-700 hover:text-indigo-700 hover:underline"
            :title="bar.label"
            :to="{ name: 'ProjectDetail', params: { projectId: bar.name, view: 'dashboard' } }"
          >
            {{ bar.label }}
          </router-link>

          <div class="relative h-5 flex-1 rounded bg-gray-100">
            <div
              class="absolute inset-y-0 rounded"
              :style="{ left: bar.left + '%', width: bar.width + '%', background: ACCENT_MUTED }"
              :title="`${bar.start} → ${bar.end}`"
            ></div>
            <!-- Progress fills the same bar rather than sitting beside it, so
                 one row still reads as one project. -->
            <div
              class="absolute inset-y-0 rounded"
              :style="{
                left: bar.left + '%',
                width: (bar.width * bar.progress) / 100 + '%',
                background: ACCENT,
              }"
            ></div>
            <span
              v-for="marker in bar.markers"
              :key="marker.at"
              class="absolute top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rotate-45 border border-white bg-gray-900"
              :style="{ left: marker.left + '%' }"
              :title="`Go-live ${marker.at}`"
            ></span>
          </div>
        </div>
      </div>

      <p class="ml-40 mt-2 text-[11px] text-gray-400">
        Bars span each project's expected start and end; the diamond is the earliest module
        go-live still outstanding.
      </p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { ACCENT, ACCENT_MUTED } from '@/utils/charts'
import { formatDate } from '@/utils/format'

const props = defineProps({
  projects: { type: Array, default: () => [] },
})

function toDate(value) {
  if (!value) return null
  const [y, m, d] = String(value).slice(0, 10).split('-').map(Number)
  if (!y || !m || !d) return null
  // Local parts: new Date('YYYY-MM-DD') parses as UTC and shifts the day west
  // of the meridian — the same trap utils/format.js documents.
  return new Date(y, m - 1, d)
}

const dated = computed(() =>
  props.projects
    .map((project) => ({
      project,
      start: toDate(project.expected_start_date),
      end: toDate(project.expected_end_date),
    }))
    .filter((row) => row.start && row.end && row.end >= row.start)
)

const range = computed(() => {
  if (!dated.value.length) return null
  let min = dated.value[0].start
  let max = dated.value[0].end
  for (const row of dated.value) {
    if (row.start < min) min = row.start
    if (row.end > max) max = row.end
  }
  // A single-day span would divide by zero.
  const span = Math.max(max - min, 86400000)
  return { min, max, span }
})

function positionOf(date) {
  if (!range.value || !date) return null
  return ((date - range.value.min) / range.value.span) * 100
}

const bars = computed(() =>
  dated.value.map(({ project, start, end }) => {
    const left = positionOf(start)
    const right = positionOf(end)
    const goLive = toDate(project.next_go_live)
    const markerLeft = positionOf(goLive)
    return {
      name: project.name,
      label: project.project_name || project.name,
      start: formatDate(project.expected_start_date),
      end: formatDate(project.expected_end_date),
      left,
      // Always leave something visible for a same-day project.
      width: Math.max(right - left, 0.5),
      progress: Math.min(Math.max(Number(project.percent_complete) || 0, 0), 100),
      markers:
        markerLeft !== null && markerLeft >= 0 && markerLeft <= 100
          ? [{ at: project.next_go_live, left: markerLeft }]
          : [],
    }
  })
)

const todayLeft = computed(() => {
  const position = positionOf(new Date(new Date().setHours(0, 0, 0, 0)))
  return position !== null && position >= 0 && position <= 100 ? position : null
})

const ticks = computed(() => {
  if (!range.value) return []
  const out = []
  const cursor = new Date(range.value.min.getFullYear(), range.value.min.getMonth(), 1)
  while (cursor <= range.value.max) {
    const position = positionOf(cursor)
    if (position !== null && position >= 0 && position <= 97) {
      out.push({
        at: cursor.toISOString().slice(0, 7),
        left: position,
        label: cursor.toLocaleDateString(undefined, { month: 'short' }),
      })
    }
    cursor.setMonth(cursor.getMonth() + 1)
  }
  return out
})
</script>
