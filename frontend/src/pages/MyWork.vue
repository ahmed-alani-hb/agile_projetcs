<template>
  <div class="flex h-full flex-col">
    <AppHeader />

    <main class="mx-auto w-full max-w-5xl flex-1 overflow-y-auto px-4 py-8 sm:px-6">
      <div class="mb-6 flex items-center justify-between">
        <div>
          <h1 class="text-xl font-semibold text-gray-900">My Work</h1>
          <p class="mt-1 text-sm text-gray-500">
            {{ work.data?.total || 0 }} open task{{ (work.data?.total || 0) === 1 ? '' : 's' }}
            assigned to you across every project
          </p>
        </div>
        <Button variant="subtle" :loading="work.loading" @click="work.reload()">Refresh</Button>
      </div>

      <div
        v-if="work.data && !work.data.employee"
        class="mb-4 rounded-lg border border-orange-200 bg-orange-50 px-3 py-2 text-xs text-orange-800"
      >
        ⚠️ No Employee record is linked to your user, so tasks where you are the SME can't be
        matched — only direct assignments are shown.
      </div>

      <div v-if="work.loading && !work.data" class="py-16 text-center text-sm text-gray-500">
        Loading your work…
      </div>

      <div
        v-else-if="!work.data?.total"
        class="rounded-xl border border-dashed border-gray-300 py-16 text-center"
      >
        <p class="text-3xl">🎉</p>
        <p class="mt-2 text-sm font-medium text-gray-700">Nothing assigned to you</p>
        <p class="mt-1 text-sm text-gray-500">Enjoy the quiet.</p>
      </div>

      <div v-else class="space-y-5">
        <section v-for="bucket in BUCKETS" :key="bucket.key">
          <template v-if="work.data.buckets[bucket.key]?.length">
            <h2 class="mb-2 flex items-center gap-2 text-sm font-semibold" :class="bucket.class">
              <span>{{ bucket.icon }}</span>
              {{ bucket.label }}
              <span class="rounded-full bg-gray-100 px-1.5 py-0.5 text-[11px] text-gray-600">
                {{ work.data.buckets[bucket.key].length }}
              </span>
            </h2>
            <ul class="divide-y divide-gray-100 overflow-hidden rounded-lg border border-gray-200 bg-white">
              <li
                v-for="task in work.data.buckets[bucket.key]"
                :key="task.name"
                class="flex cursor-pointer items-center gap-3 px-3 py-2 hover:bg-gray-50"
                @click="openTask(task)"
              >
                <span class="hidden w-24 shrink-0 truncate font-mono text-[11px] text-gray-400 sm:block">
                  {{ task.name }}
                </span>
                <span class="min-w-0 flex-1 truncate text-sm text-gray-900">{{ task.subject }}</span>
                <span v-if="task.is_blocked" title="Blocked">⛔</span>
                <span
                  v-if="task.complexity_points"
                  class="shrink-0 rounded-full px-1.5 py-0.5 text-[11px] font-semibold"
                  :class="POINT_COLORS[task.complexity_points] || 'bg-gray-100 text-gray-700'"
                >
                  {{ task.complexity_points }}
                </span>
                <span
                  class="hidden shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium sm:inline"
                  :class="(STATUS_META[task.status] || STATUS_META.Backlog).pill"
                >
                  {{ task.status }}
                </span>
                <router-link
                  :to="{ name: 'ProjectDetail', params: { projectId: task.project, view: 'board' } }"
                  class="hidden max-w-[140px] shrink-0 truncate text-[11px] text-gray-500 hover:text-indigo-600 md:block"
                  @click.stop
                >
                  {{ task.project_name || task.project }}
                </router-link>
                <span
                  class="w-16 shrink-0 text-right text-[11px]"
                  :class="bucket.key === 'overdue' ? 'font-medium text-red-600' : 'text-gray-500'"
                >
                  {{ formatDate(task.exp_end_date) }}
                </span>
              </li>
            </ul>
          </template>
        </section>
      </div>
    </main>

    <TaskDetailModal
      v-model="showDetail"
      :task-name="selectedTask"
      @task-updated="work.reload()"
    />
  </div>
</template>

<script setup>
import { defineAsyncComponent, ref } from 'vue'
import { Button, createResource } from 'frappe-ui'
import AppHeader from '@/components/AppHeader.vue'

const TaskDetailModal = defineAsyncComponent(() =>
  import('@/components/TaskDetailModal.vue')
)
import { STATUS_META, POINT_COLORS } from '@/utils/statuses'
import { formatDate } from '@/utils/format'
import { toast, errorMessage } from '@/utils/toast'

const BUCKETS = [
  { key: 'overdue', label: 'Overdue', icon: '🔴', class: 'text-red-700' },
  { key: 'blocked', label: 'Blocked', icon: '⛔', class: 'text-red-700' },
  { key: 'today', label: 'Due today', icon: '📅', class: 'text-orange-700' },
  { key: 'this_week', label: 'This week', icon: '🗓', class: 'text-gray-800' },
  { key: 'later', label: 'Later / no due date', icon: '📥', class: 'text-gray-600' },
]

const work = createResource({
  url: 'agile_projects.views.get_my_work',
  auto: true,
  onError(err) {
    toast({ title: 'Failed to load your work', text: errorMessage(err), type: 'error' })
  },
})

const showDetail = ref(false)
const selectedTask = ref(null)

function openTask(task) {
  selectedTask.value = task.name
  showDetail.value = true
}
</script>
