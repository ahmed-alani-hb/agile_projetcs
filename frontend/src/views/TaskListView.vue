<template>
  <div class="h-full overflow-y-auto px-4 py-4 sm:px-6">
    <div class="mb-3 flex items-center gap-2">
      <span class="text-sm text-gray-500">
        {{ tasks.data?.total || 0 }} task{{ (tasks.data?.total || 0) === 1 ? '' : 's' }}
      </span>
      <span class="flex-1"></span>
      <label class="text-xs text-gray-500">Group by</label>
      <select
        v-model="groupBy"
        class="rounded-md border-gray-300 py-1 text-xs focus:border-indigo-500 focus:ring-indigo-500"
      >
        <option value="status">Status</option>
        <option value="priority">Priority</option>
        <option value="sme_responsible">SME</option>
        <option value="">Nothing</option>
      </select>
    </div>

    <div v-if="tasks.loading && !rows.length" class="py-16 text-center text-sm text-gray-500">
      Loading tasks…
    </div>
    <p v-else-if="!rows.length" class="py-16 text-center text-sm text-gray-400">
      No tasks match these filters.
    </p>

    <div v-else class="space-y-4">
      <section
        v-for="group in groups"
        :key="group.key"
        class="overflow-hidden rounded-lg border border-gray-200 bg-white"
      >
        <button
          class="flex w-full items-center gap-2 border-b border-gray-100 bg-gray-50 px-3 py-2 text-left"
          @click="toggle(group.key)"
        >
          <span class="text-xs text-gray-400">{{ collapsed[group.key] ? '▸' : '▾' }}</span>
          <span
            v-if="groupBy === 'status'"
            class="h-2 w-2 rounded-full"
            :class="(STATUS_META[group.key] || STATUS_META.Backlog).dot"
          ></span>
          <span class="text-sm font-semibold text-gray-800">{{ group.label }}</span>
          <span class="rounded-full bg-white px-1.5 py-0.5 text-[11px] text-gray-500">
            {{ group.tasks.length }}
          </span>
          <span v-if="group.points" class="text-[11px] text-gray-400">{{ group.points }} pts</span>
        </button>

        <ul v-show="!collapsed[group.key]" class="divide-y divide-gray-100">
          <li
            v-for="task in group.tasks"
            :key="task.name"
            class="flex cursor-pointer items-center gap-3 px-3 py-2 hover:bg-gray-50"
            @click="$emit('open-task', task)"
          >
            <span class="w-24 shrink-0 truncate font-mono text-[11px] text-gray-400">
              {{ task.name }}
            </span>
            <span class="min-w-0 flex-1 truncate text-sm text-gray-900">{{ task.subject }}</span>
            <span v-if="task.is_blocked" class="shrink-0 text-xs" title="Blocked">⛔</span>
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
            <span
              class="hidden w-20 shrink-0 text-right text-[11px] sm:inline"
              :class="isOverdue(task.exp_end_date) && task.status !== 'Done' ? 'text-red-600' : 'text-gray-500'"
            >
              {{ formatDate(task.exp_end_date) }}
            </span>
            <span
              v-if="task.sme_responsible"
              class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-[10px] font-semibold text-indigo-700"
              :title="task.sme_name || task.sme_responsible"
            >
              {{ initials(task.sme_name || task.sme_responsible) }}
            </span>
          </li>
        </ul>
      </section>
    </div>

    <div v-if="hasMore" class="mt-4 text-center">
      <Button variant="subtle" :loading="tasks.loading" @click="loadMore">Load more</Button>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { Button, createResource } from 'frappe-ui'
import { STATUSES, STATUS_META, POINT_COLORS, PRIORITIES } from '@/utils/statuses'
import { formatDate, initials, isOverdue } from '@/utils/format'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  project: { type: String, required: true },
  filters: { type: Object, default: () => ({}) },
})

defineEmits(['open-task', 'changed'])

const PAGE = 100
const groupBy = ref('status')
const collapsed = reactive({})
const rows = ref([])
const start = ref(0)

const tasks = createResource({
  url: 'agile_projects.views.get_tasks_list',
  makeParams: () => ({
    project: props.project,
    filters: props.filters,
    order_by: 'exp_end_date asc',
    start: start.value,
    page_length: PAGE,
  }),
  auto: true,
  onSuccess(data) {
    rows.value = start.value === 0 ? data.tasks : [...rows.value, ...data.tasks]
  },
  onError(err) {
    toast({ title: 'Failed to load tasks', text: errorMessage(err), type: 'error' })
  },
})

watch(
  () => [props.project, props.filters],
  () => {
    start.value = 0
    tasks.reload()
  },
  { deep: true }
)

const hasMore = computed(() => rows.value.length < (tasks.data?.total || 0))

function loadMore() {
  start.value = rows.value.length
  tasks.reload()
}

const groups = computed(() => {
  if (!groupBy.value) {
    return [{ key: 'all', label: 'All tasks', tasks: rows.value, points: points(rows.value) }]
  }
  const buckets = new Map()
  for (const task of rows.value) {
    const key = task[groupBy.value] || '—'
    if (!buckets.has(key)) buckets.set(key, [])
    buckets.get(key).push(task)
  }
  const order =
    groupBy.value === 'status' ? STATUSES : groupBy.value === 'priority' ? PRIORITIES : null
  let keys = [...buckets.keys()]
  if (order) {
    keys.sort((a, b) => order.indexOf(a) - order.indexOf(b))
  } else {
    keys.sort()
  }
  return keys.map((key) => {
    const list = buckets.get(key)
    return {
      key,
      label: groupBy.value === 'sme_responsible' ? list[0].sme_name || key : key,
      tasks: list,
      points: points(list),
    }
  })
})

function points(list) {
  return list.reduce((sum, t) => sum + (parseInt(t.complexity_points) || 0), 0)
}

function toggle(key) {
  collapsed[key] = !collapsed[key]
}

defineExpose({
  reload: () => {
    start.value = 0
    tasks.reload()
  },
})
</script>
