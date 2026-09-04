<template>
  <div class="flex h-full flex-col">
    <AppHeader />
    <main class="thin-scrollbar mx-auto w-full max-w-7xl flex-1 overflow-y-auto px-4 py-8 sm:px-6">
      <div class="mb-6 flex items-center justify-between">
        <div>
          <h1 class="text-xl font-semibold text-gray-900">Portfolio</h1>
          <p class="mt-1 text-sm text-gray-500">Every rollout, and what is about to go wrong</p>
        </div>
        <Button variant="subtle" :loading="metrics.loading" @click="metrics.reload()">
          Refresh
        </Button>
      </div>

      <div v-if="metrics.loading && !data" class="py-16 text-center text-sm text-gray-500">
        Loading portfolio…
      </div>

      <template v-else-if="data">
        <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatTile label="Projects" :value="String(totals.projects)" />
          <StatTile
            label="Modules live"
            :value="`${totals.modules_live}/${totals.modules}`"
          />
          <StatTile
            label="At risk"
            :value="String(totals.modules_at_risk)"
            hint="past target go-live"
            :tone="totals.modules_at_risk ? 'warn' : 'plain'"
          />
          <StatTile
            label="Blocked tasks"
            :value="String(totals.blocked_tasks)"
            :hint="`of ${totals.total_tasks} total`"
            :tone="totals.blocked_tasks ? 'warn' : 'plain'"
          />
        </div>

        <!-- The list of specifics that needs names and dates, so not a chart. -->
        <section
          v-if="data.at_risk.length"
          class="mt-5 rounded-xl border border-red-200 bg-red-50/50 p-4"
        >
          <h2 class="text-sm font-semibold text-red-900">Modules past target go-live</h2>
          <ul class="mt-2 divide-y divide-red-100">
            <li v-for="module in data.at_risk" :key="module.module" class="py-1.5">
              <router-link
                class="flex flex-wrap items-center gap-2 text-sm text-red-800 hover:underline"
                :to="{ name: 'ProjectDetail', params: { projectId: module.project, view: 'modules' } }"
              >
                <span class="font-medium">{{ module.module_name }}</span>
                <span class="text-red-600">· {{ module.gate }}</span>
                <span class="text-xs text-red-500">{{ module.project }}</span>
                <span class="flex-1"></span>
                <span class="text-xs font-medium">{{ module.days_late }}d late</span>
              </router-link>
            </li>
          </ul>
        </section>

        <section class="mt-5 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <AxisChart :config="gateConfig" />
        </section>

        <!-- Projects on one timeline: the overlap a per-project Gantt hides. -->
        <section class="mt-5 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <h2 class="mb-3 text-sm font-semibold text-gray-900">Delivery timeline</h2>
          <PortfolioTimeline :projects="data.projects" />
        </section>

        <section class="mt-5">
          <h2 class="mb-2 text-sm font-semibold text-gray-900">Projects</h2>
          <div class="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
            <table class="min-w-full text-sm">
              <thead class="border-b border-gray-200 bg-gray-50 text-left text-xs text-gray-500">
                <tr>
                  <th class="px-3 py-2 font-medium">Project</th>
                  <th class="px-3 py-2 font-medium">Progress</th>
                  <th class="px-3 py-2 font-medium">Tasks</th>
                  <th class="px-3 py-2 font-medium">Blocked</th>
                  <th class="px-3 py-2 font-medium">Modules live</th>
                  <th class="px-3 py-2 font-medium">Next go-live</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
                <tr v-for="project in data.projects" :key="project.name" class="hover:bg-gray-50">
                  <td class="px-3 py-2">
                    <router-link
                      class="font-medium text-indigo-700 hover:underline"
                      :to="{ name: 'ProjectDetail', params: { projectId: project.name, view: 'dashboard' } }"
                    >
                      {{ project.project_name || project.name }}
                    </router-link>
                  </td>
                  <td class="px-3 py-2 text-gray-700">
                    {{ Math.round(project.percent_complete || 0) }}%
                  </td>
                  <td class="px-3 py-2 text-gray-700">
                    {{ project.done_tasks }}/{{ project.total_tasks }}
                  </td>
                  <td class="px-3 py-2" :class="project.blocked_tasks ? 'font-medium text-red-600' : 'text-gray-400'">
                    {{ project.blocked_tasks || '—' }}
                  </td>
                  <td class="px-3 py-2 text-gray-700">
                    {{ project.module_live }}/{{ project.module_total }}
                  </td>
                  <td class="px-3 py-2 text-gray-700">
                    {{ project.next_go_live ? formatDate(project.next_go_live) : '—' }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>
    </main>
  </div>
</template>

<script setup>
import { computed, h } from 'vue'
import { AxisChart, Button, createResource } from 'frappe-ui'
import AppHeader from '@/components/AppHeader.vue'
import PortfolioTimeline from '@/components/PortfolioTimeline.vue'
import { magnitudeBars } from '@/utils/charts'
import { formatDate } from '@/utils/format'
import { toast, errorMessage } from '@/utils/toast'

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
  url: 'agile_projects.metrics.get_portfolio_metrics',
  auto: true,
  onError(err) {
    toast({ title: 'Failed to load portfolio', text: errorMessage(err), type: 'error' })
  },
})

const data = computed(() => metrics.data)
const totals = computed(() => data.value?.totals || {})

const gateConfig = computed(() =>
  magnitudeBars({
    title: 'Modules by gate',
    subtitle: 'across every project',
    rows: data.value?.gate_mix || [],
    seriesName: 'Modules',
  })
)
</script>
