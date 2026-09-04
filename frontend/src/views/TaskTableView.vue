<template>
  <div class="flex h-full flex-col">
    <!-- toolbar -->
    <div class="flex items-center gap-2 border-b border-gray-200 bg-white px-4 py-1.5 sm:px-6">
      <span class="text-xs text-gray-500">
        {{ rows.length }}{{ hasMore ? '+' : '' }} task{{ rows.length === 1 ? '' : 's' }}
      </span>
      <span class="flex-1"></span>
      <Dropdown :options="columnOptions">
        <Button variant="ghost" size="sm">Columns ▾</Button>
      </Dropdown>
    </div>

    <!-- bulk action bar -->
    <div
      v-if="selected.size"
      class="flex flex-wrap items-center gap-2 border-b border-indigo-200 bg-indigo-50 px-4 py-2 sm:px-6"
    >
      <span class="text-sm font-medium text-indigo-900">{{ selected.size }} selected</span>
      <select
        class="rounded-md border-gray-300 py-1 text-xs focus:border-indigo-500 focus:ring-indigo-500"
        :value="''"
        @change="bulkSet('status', $event.target.value), ($event.target.value = '')"
      >
        <option value="" disabled>Set status…</option>
        <option v-for="s in STATUSES" :key="s" :value="s">{{ s }}</option>
      </select>
      <select
        class="rounded-md border-gray-300 py-1 text-xs focus:border-indigo-500 focus:ring-indigo-500"
        :value="''"
        @change="bulkSet('priority', $event.target.value), ($event.target.value = '')"
      >
        <option value="" disabled>Set priority…</option>
        <option v-for="p in PRIORITIES" :key="p" :value="p">{{ p }}</option>
      </select>
      <select
        class="rounded-md border-gray-300 py-1 text-xs focus:border-indigo-500 focus:ring-indigo-500"
        :value="''"
        @change="bulkSet('complexity_points', $event.target.value), ($event.target.value = '')"
      >
        <option value="" disabled>Set points…</option>
        <option v-for="p in POINT_OPTIONS" :key="p" :value="p">{{ p }} pts</option>
      </select>
      <span class="flex-1"></span>
      <Button variant="ghost" size="sm" @click="selected.clear()">Clear selection</Button>
    </div>

    <!-- grid -->
    <div class="min-h-0 flex-1 overflow-auto">
      <table class="w-full border-collapse text-sm">
        <thead class="sticky top-0 z-10 bg-gray-50 text-left">
          <tr class="border-b border-gray-200">
            <th class="w-9 px-2 py-2">
              <input
                type="checkbox"
                class="h-3.5 w-3.5 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                :checked="allSelected"
                @change="toggleAll($event.target.checked)"
              />
            </th>
            <th
              v-for="col in visibleColumns"
              :key="col.key"
              class="whitespace-nowrap px-2 py-2 text-xs font-semibold text-gray-600"
              :style="{ width: col.width }"
            >
              {{ col.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="task in rows"
            :key="task.name"
            class="border-b border-gray-100 hover:bg-gray-50"
            :class="{ 'bg-indigo-50/40': selected.has(task.name) }"
          >
            <td class="px-2 py-1">
              <input
                type="checkbox"
                class="h-3.5 w-3.5 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                :checked="selected.has(task.name)"
                @change="toggleOne(task.name, $event.target.checked)"
              />
            </td>

            <td v-for="col in visibleColumns" :key="col.key" class="px-2 py-1">
              <!-- id -->
              <button
                v-if="col.key === 'name'"
                class="font-mono text-[11px] text-indigo-600 hover:underline"
                @click="$emit('open-task', task)"
              >
                {{ task.name }}
              </button>

              <!-- subject -->
              <div v-else-if="col.key === 'subject'" class="flex items-center gap-1.5">
                <span v-if="task.is_blocked" title="Blocked">⛔</span>
                <input
                  :value="task.subject"
                  class="w-full min-w-0 border-0 bg-transparent px-1 py-0.5 text-sm focus:rounded focus:bg-white focus:ring-1 focus:ring-indigo-400"
                  @change="saveCell(task, 'subject', $event.target.value)"
                />
              </div>

              <!-- status -->
              <select
                v-else-if="col.key === 'status'"
                :value="task.status"
                class="w-full rounded border-0 bg-transparent px-1 py-0.5 text-xs focus:bg-white focus:ring-1 focus:ring-indigo-400"
                @change="saveStatus(task, $event.target.value)"
              >
                <option v-for="s in STATUSES" :key="s" :value="s">{{ s }}</option>
              </select>

              <!-- priority -->
              <select
                v-else-if="col.key === 'priority'"
                :value="task.priority || ''"
                class="w-full rounded border-0 bg-transparent px-1 py-0.5 text-xs focus:bg-white focus:ring-1 focus:ring-indigo-400"
                @change="saveCell(task, 'priority', $event.target.value)"
              >
                <option value="">—</option>
                <option v-for="p in PRIORITIES" :key="p" :value="p">{{ p }}</option>
              </select>

              <!-- points -->
              <select
                v-else-if="col.key === 'complexity_points'"
                :value="task.complexity_points || ''"
                class="w-full rounded border-0 bg-transparent px-1 py-0.5 text-xs focus:bg-white focus:ring-1 focus:ring-indigo-400"
                @change="saveCell(task, 'complexity_points', $event.target.value)"
              >
                <option value="">—</option>
                <option v-for="p in POINT_OPTIONS" :key="p" :value="p">{{ p }}</option>
              </select>

              <!-- sme -->
              <select
                v-else-if="col.key === 'sme_responsible'"
                :value="task.sme_responsible || ''"
                class="w-full rounded border-0 bg-transparent px-1 py-0.5 text-xs focus:bg-white focus:ring-1 focus:ring-indigo-400"
                @change="saveCell(task, 'sme_responsible', $event.target.value)"
              >
                <option value="">Unassigned</option>
                <option v-for="e in employees.data || []" :key="e.name" :value="e.name">
                  {{ e.employee_name }}
                </option>
              </select>

              <!-- dates -->
              <input
                v-else-if="col.key === 'exp_start_date' || col.key === 'exp_end_date'"
                type="date"
                :value="toDateInput(task[col.key])"
                class="w-full rounded border-0 bg-transparent px-1 py-0.5 text-xs focus:bg-white focus:ring-1 focus:ring-indigo-400"
                :class="
                  col.key === 'exp_end_date' && isOverdue(task[col.key]) && task.status !== 'Done'
                    ? 'text-red-600'
                    : 'text-gray-700'
                "
                @change="saveCell(task, col.key, $event.target.value)"
              />

              <!-- progress -->
              <div v-else-if="col.key === 'progress'" class="flex items-center gap-1.5">
                <div class="h-1.5 w-14 overflow-hidden rounded-full bg-gray-200">
                  <div
                    class="h-full rounded-full bg-indigo-500"
                    :style="{ width: Math.min(task.progress || 0, 100) + '%' }"
                  ></div>
                </div>
                <span class="text-[11px] text-gray-500">{{ Math.round(task.progress || 0) }}%</span>
              </div>

              <span v-else-if="col.key === 'actual_time'" class="text-xs text-gray-500">
                {{ formatHours(task.actual_time) }}
              </span>

              <span v-else class="text-xs text-gray-500">{{ task[col.key] }}</span>
            </td>
          </tr>
        </tbody>
      </table>

      <p v-if="!rows.length && !tasks.loading" class="py-16 text-center text-sm text-gray-400">
        No tasks match these filters.
      </p>
      <div v-if="hasMore" class="p-4 text-center">
        <Button variant="subtle" :loading="tasks.loading" @click="loadMore">Load more</Button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Button, Dropdown, createResource } from 'frappe-ui'
import { STATUSES, PRIORITIES, POINT_OPTIONS } from '@/utils/statuses'
import { formatHours, isOverdue, toDateInput } from '@/utils/format'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  project: { type: String, required: true },
  filters: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['open-task', 'changed'])

const ALL_COLUMNS = [
  { key: 'name', label: 'ID', width: '110px', fixed: true },
  { key: 'subject', label: 'Subject', width: 'auto', fixed: true },
  { key: 'status', label: 'Status', width: '150px' },
  { key: 'priority', label: 'Priority', width: '110px' },
  { key: 'complexity_points', label: 'Points', width: '80px' },
  { key: 'sme_responsible', label: 'SME', width: '160px' },
  { key: 'exp_start_date', label: 'Start', width: '130px' },
  { key: 'exp_end_date', label: 'Due', width: '130px' },
  { key: 'progress', label: 'Progress', width: '110px' },
  { key: 'actual_time', label: 'Hours', width: '80px' },
]

const hidden = reactive({ exp_start_date: true, actual_time: true })

const visibleColumns = computed(() => ALL_COLUMNS.filter((c) => !hidden[c.key]))

const columnOptions = computed(() =>
  ALL_COLUMNS.filter((c) => !c.fixed).map((c) => ({
    label: `${hidden[c.key] ? '☐' : '☑'} ${c.label}`,
    onClick: () => {
      hidden[c.key] = !hidden[c.key]
    },
  }))
)

const PAGE = 100
const rows = ref([])
const start = ref(0)
const selected = reactive(new Set())

const tasks = createResource({
  url: 'agile_projects.views.get_tasks_list',
  makeParams: () => ({
    project: props.project,
    filters: props.filters,
    order_by: 'modified desc',
    start: start.value,
    page_length: PAGE,
  }),
  auto: true,
  onSuccess(data) {
    // use the server-echoed offset, not the possibly-advanced local ref
    rows.value = data.start === 0 ? data.tasks : [...rows.value, ...data.tasks]
  },
  onError(err) {
    toast({ title: 'Failed to load tasks', text: errorMessage(err), type: 'error' })
  },
})

const employees = createResource({
  url: 'agile_projects.api.get_employees',
  cache: 'agile:employees',
})

onMounted(() => {
  if (!employees.data && !employees.loading) employees.fetch()
})

watch(
  () => [props.project, props.filters],
  () => {
    start.value = 0
    selected.clear()
    tasks.reload()
  },
  { deep: true }
)

const hasMore = computed(() => !!tasks.data?.has_more)
const allSelected = computed(() => rows.value.length > 0 && selected.size === rows.value.length)

function loadMore() {
  start.value = rows.value.length
  tasks.reload()
}

function toggleAll(checked) {
  selected.clear()
  if (checked) rows.value.forEach((t) => selected.add(t.name))
}

function toggleOne(name, checked) {
  if (checked) selected.add(name)
  else selected.delete(name)
}

// ---- editing ----
const update = createResource({ url: 'agile_projects.api.update_task' })
const statusResource = createResource({ url: 'agile_projects.api.update_task_status' })
const bulk = createResource({ url: 'agile_projects.views.bulk_update_tasks' })

function saveCell(task, field, value) {
  const previous = task[field]
  task[field] = value
  update
    .submit({ task: task.name, fields: { [field]: value } })
    .then(() => emit('changed'))
    .catch((err) => {
      task[field] = previous
      toast({ title: 'Could not save', text: errorMessage(err), type: 'error' })
    })
}

function saveStatus(task, status) {
  const previous = task.status
  task.status = status
  statusResource
    .submit({ task: task.name, status })
    .then(() => emit('changed'))
    .catch((err) => {
      task.status = previous
      toast({
        title: 'Status change rejected',
        text: errorMessage(err),
        type: 'error',
        timeout: 8000,
      })
    })
}

function bulkSet(field, value) {
  if (!value || !selected.size) return
  bulk
    .submit({ tasks: [...selected], fields: { [field]: value } })
    .then((data) => {
      const failed = data.failed || []
      if (failed.length) {
        toast({
          title: `${data.updated.length} updated, ${failed.length} rejected`,
          text: failed.map((f) => `${f.task}: ${f.error}`).join('\n'),
          type: 'warning',
          timeout: 10000,
        })
      } else {
        toast({ title: `${data.updated.length} tasks updated`, type: 'success', timeout: 2500 })
      }
      selected.clear()
      start.value = 0
      tasks.reload()
      emit('changed')
    })
    .catch((err) => {
      toast({ title: 'Bulk update failed', text: errorMessage(err), type: 'error' })
    })
}

defineExpose({
  reload: () => {
    start.value = 0
    tasks.reload()
  },
})
</script>
