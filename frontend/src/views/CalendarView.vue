<template>
  <div class="h-full overflow-y-auto p-4 sm:p-6">
    <div v-if="tasks.loading && !events.length" class="py-16 text-center text-sm text-gray-500">
      Loading calendar…
    </div>
    <div v-else class="rounded-lg border border-gray-200 bg-white p-2">
      <p class="px-2 pb-2 text-xs text-gray-500">
        Tasks are placed on their due date. {{ events.length }} scheduled ·
        {{ undatedCount }} without a due date. Click a task to edit it.
      </p>
      <Calendar
        :events="events"
        :onClick="onEventClick"
        :config="{ defaultMode: 'Month', isEditMode: false, disableModes: ['Day'] }"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, watch } from 'vue'
import { Calendar, createResource } from 'frappe-ui'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  project: { type: String, required: true },
  filters: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['open-task', 'changed'])

const STATUS_COLOR = {
  Backlog: 'gray',
  'To Do': 'blue',
  'In Progress': 'amber',
  'QA/Code Review': 'violet',
  Blocked: 'red',
  Done: 'green',
}

const tasks = createResource({
  url: 'agile_projects.views.get_tasks_list',
  makeParams: () => ({
    project: props.project,
    filters: props.filters,
    order_by: 'exp_end_date asc',
    page_length: 500,
  }),
  auto: true,
  onError(err) {
    toast({ title: 'Failed to load calendar', text: errorMessage(err), type: 'error' })
  },
})

watch(
  () => [props.project, props.filters],
  () => tasks.reload(),
  { deep: true }
)

const allTasks = computed(() => tasks.data?.tasks || [])

const events = computed(() =>
  allTasks.value
    .filter((task) => task.exp_end_date)
    .map((task) => ({
      id: task.name,
      title: task.subject,
      participant: task.sme_name || '',
      // tasks are all-day; the calendar still expects a time window
      fromDate: task.exp_start_date || task.exp_end_date,
      toDate: task.exp_end_date,
      fromTime: '09:00',
      toTime: '17:00',
      color: STATUS_COLOR[task.status] || 'gray',
    }))
)

const undatedCount = computed(() => allTasks.value.filter((t) => !t.exp_end_date).length)

function onEventClick(event) {
  const id = event?.id || event
  const task = allTasks.value.find((t) => t.name === id)
  if (task) emit('open-task', task)
}

defineExpose({ reload: () => tasks.reload() })
</script>
