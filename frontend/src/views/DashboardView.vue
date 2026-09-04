<template>
  <div class="thin-scrollbar h-full overflow-y-auto bg-gray-50">
    <div class="mx-auto max-w-6xl space-y-5 px-4 py-5 sm:px-6">
      <div v-if="metrics.loading && !data" class="py-16 text-center text-sm text-gray-500">
        Loading metrics…
      </div>

      <template v-else-if="data">
        <!-- Headline numbers are numbers, not one-bar charts. -->
        <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatTile label="Complete" :value="percentText" :hint="pointsHint" />
          <StatTile
            label="Modules live"
            :value="`${data.modules.live}/${data.modules.total}`"
            :hint="readinessHint"
          />
          <StatTile
            label="Next go-live"
            :value="goLiveText"
            :hint="data.modules.next_go_live || 'none scheduled'"
            :tone="goLiveTone"
          />
          <StatTile
            label="Blocked"
            :value="String(data.tasks.blocked_tasks)"
            :hint="`${data.tasks.overdue_tasks} overdue`"
            :tone="data.tasks.blocked_tasks ? 'warn' : 'plain'"
          />
        </div>

        <!-- Modules past their go-live: a list of specifics, so a table. -->
        <section
          v-if="data.modules.at_risk.length"
          class="rounded-xl border border-red-200 bg-red-50/50 p-4"
        >
          <h3 class="text-sm font-semibold text-red-900">
            {{ data.modules.at_risk.length }} module{{ data.modules.at_risk.length === 1 ? '' : 's' }}
            past target go-live
          </h3>
          <ul class="mt-2 space-y-1">
            <li
              v-for="module in data.modules.at_risk"
              :key="module.name"
              class="flex items-center gap-2 text-sm text-red-800"
            >
              <span class="font-medium">{{ module.module_name }}</span>
              <span class="text-red-600">· {{ module.gate }}</span>
              <span class="flex-1"></span>
              <span class="text-xs">{{ module.days_late }}d late</span>
            </li>
          </ul>
        </section>

        <!-- Two measures of different scale get two charts, never two axes. -->
        <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ChartCard>
            <AxisChart :config="velocityConfig" />
            <p class="mt-1 px-1 text-[11px] text-gray-400">
              Points completed per week, from each task's completion date — available for the
              whole history, not just since tracking began.
            </p>
          </ChartCard>

          <ChartCard>
            <AxisChart :config="statusConfig" />
          </ChartCard>
        </div>

        <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ChartCard>
            <AxisChart :config="gateConfig" />
          </ChartCard>

          <ChartCard>
            <AxisChart v-if="effortConfig" :config="effortConfig" />
            <p v-else class="py-12 text-center text-sm text-gray-500">
              No hours logged yet.
            </p>
            <p class="mt-1 px-1 text-[11px] text-gray-400">
              Submitted timesheet hours against estimate. Aggregated per module rather than
              plotted over time: logged hours record a duration faithfully, but their
              timestamps are synthesised.
            </p>
          </ChartCard>
        </div>

        <!-- Lead time is two numbers; a distribution chart would overstate it. -->
        <ChartCard>
          <div class="flex flex-wrap items-baseline gap-x-8 gap-y-2 px-1">
            <div>
              <h3 class="text-sm font-semibold text-gray-900">Lead time</h3>
              <p class="text-[11px] text-gray-400">Created to done, across {{ data.tasks.lead_time.count }} finished tasks</p>
            </div>
            <span class="flex-1"></span>
            <div>
              <p class="text-lg font-semibold text-gray-900">{{ formatDays(data.tasks.lead_time.median) }}</p>
              <p class="text-[11px] text-gray-500">median</p>
            </div>
            <div>
              <p class="text-lg font-semibold text-gray-900">{{ formatDays(data.tasks.lead_time.p85) }}</p>
              <p class="text-[11px] text-gray-500">85th percentile</p>
            </div>
          </div>
        </ChartCard>

        <!-- Flow: the one section that genuinely cannot see the past. -->
        <ChartCard>
          <div class="mb-2 flex flex-wrap items-center gap-2 px-1">
            <h3 class="text-sm font-semibold text-gray-900">Flow</h3>
            <span class="flex-1"></span>
            <Button variant="subtle" size="sm" :loading="snapshot.loading" @click="takeSnapshot">
              Snapshot today
            </Button>
          </div>

          <p v-if="!flowRows.length" class="py-10 text-center text-sm text-gray-500">
            No history yet. Flow is the one thing that cannot be reconstructed after the fact —
            a daily snapshot builds it from here. Take one now to start the series.
          </p>
          <template v-else>
            <AxisChart :config="flowConfig" />
            <p class="mt-1 px-1 text-[11px] text-gray-400">
              Tracking since {{ flow.data.history_starts_on }}. Grouped into the four states a
              rollout steers on; the full six-status split is the chart above.
            </p>
          </template>
        </ChartCard>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, h, watch } from 'vue'
import { AxisChart, Button, createResource } from 'frappe-ui'
import {
  ACCENT,
  ACCENT_MUTED,
  FLOW_BANDS,
  FLOW_COLORS,
  formatDays,
  magnitudeBars,
  toFlowBands,
  trendColumns,
} from '@/utils/charts'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  project: { type: String, required: true },
})

// Small local presentational helpers; not worth their own files.
const ChartCard = (_, { slots }) =>
  h('section', { class: 'rounded-xl border border-gray-200 bg-white p-4 shadow-sm' }, slots.default())

const StatTile = (props) =>
  h('div', { class: 'rounded-xl border border-gray-200 bg-white p-4 shadow-sm' }, [
    h('p', { class: 'text-[11px] font-medium uppercase tracking-wide text-gray-400' }, props.label),
    h(
      'p',
      {
        class: [
          'mt-1 text-2xl font-semibold',
          props.tone === 'warn' ? 'text-red-600' : 'text-gray-900',
        ],
      },
      props.value
    ),
    props.hint ? h('p', { class: 'mt-0.5 text-[11px] text-gray-500' }, props.hint) : null,
  ])
StatTile.props = ['label', 'value', 'hint', 'tone']

const metrics = createResource({
  url: 'agile_projects.metrics.get_project_metrics',
  makeParams: () => ({ project: props.project }),
  auto: true,
  onError(err) {
    toast({ title: 'Failed to load metrics', text: errorMessage(err), type: 'error' })
  },
})

const flow = createResource({
  url: 'agile_projects.metrics.get_flow_metrics',
  makeParams: () => ({ project: props.project }),
  auto: true,
  onError() {},
})

watch(
  () => props.project,
  () => {
    metrics.reload()
    flow.reload()
  }
)

const data = computed(() => metrics.data)

const percentText = computed(() => `${Math.round(data.value?.project?.percent_complete || 0)}%`)

const pointsHint = computed(() => {
  const t = data.value?.tasks
  return t ? `${t.done_points}/${t.total_points} points · ${t.done_tasks}/${t.total_tasks} tasks` : ''
})

const readinessHint = computed(() => {
  const readiness = data.value?.modules?.readiness
  return readiness === null || readiness === undefined ? 'no modules' : `${readiness}% gate progress`
})

const goLiveText = computed(() => {
  const days = data.value?.modules?.days_to_next_go_live
  if (days === null || days === undefined) return '—'
  if (days < 0) return `${Math.abs(days)}d late`
  return `${days}d`
})

const goLiveTone = computed(() =>
  (data.value?.modules?.days_to_next_go_live ?? 0) < 0 ? 'warn' : 'plain'
)

const velocityConfig = computed(() =>
  trendColumns({
    title: 'Velocity',
    rows: (data.value?.tasks?.velocity || []).map((point) => ({
      label: point.week.slice(5),
      value: point.value,
    })),
    seriesName: 'Points',
  })
)

// Six ordered statuses as bars, not a stack: whitespace and the axis label
// carry identity, so no palette has to separate six adjacent fills.
const statusConfig = computed(() =>
  magnitudeBars({
    title: 'Tasks by status',
    rows: data.value?.tasks?.status_mix || [],
    seriesName: 'Tasks',
  })
)

const gateConfig = computed(() =>
  magnitudeBars({
    title: 'Modules by gate',
    rows: data.value?.modules?.gate_mix || [],
    seriesName: 'Modules',
  })
)

const effortConfig = computed(() => {
  const rows = (data.value?.effort || []).filter((row) => row.logged || row.estimated)
  if (!rows.length) return null
  return {
    title: 'Effort vs estimate',
    data: rows.map((row) => ({
      module: row.label,
      Logged: row.logged,
      Estimated: row.estimated,
    })),
    // Two shades of one hue — a before/after pair, not two identities.
    colors: [ACCENT, ACCENT_MUTED],
    swapXY: true,
    xAxis: { key: 'module', type: 'category' },
    yAxis: { title: 'Hours' },
    series: [
      { name: 'Logged', type: 'bar' },
      { name: 'Estimated', type: 'bar' },
    ],
  }
})

const flowRows = computed(() => flow.data?.flow || [])

const flowConfig = computed(() => ({
  title: 'Cumulative flow',
  data: flowRows.value.map((row) => {
    const bands = toFlowBands(row)
    return {
      date: String(row.date).slice(5),
      'Not started': bands.not_started,
      'In progress': bands.in_progress,
      Done: bands.done,
      Blocked: bands.blocked,
    }
  }),
  colors: FLOW_COLORS,
  stacked: true,
  xAxis: { key: 'date', type: 'category' },
  yAxis: { title: 'Tasks' },
  series: FLOW_BANDS.map((band) => ({
    name: band.label,
    type: 'area',
    stackName: 'flow',
  })),
}))

const snapshot = createResource({ url: 'agile_projects.metrics.take_snapshot_now' })

function takeSnapshot() {
  snapshot
    .submit({ project: props.project })
    .then(() => {
      toast({ title: 'Snapshot taken', type: 'success', timeout: 2000 })
      flow.reload()
    })
    .catch((err) => {
      toast({ title: 'Could not take snapshot', text: errorMessage(err), type: 'error' })
    })
}

defineExpose({
  reload: () => {
    metrics.reload()
    flow.reload()
  },
})
</script>
