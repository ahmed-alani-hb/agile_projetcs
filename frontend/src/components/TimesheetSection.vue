<template>
  <div>
    <div class="mb-3 flex items-center justify-between">
      <p class="text-sm font-semibold text-gray-900">Time Tracking</p>
      <p class="text-xs text-gray-500">
        Total: <span class="font-semibold text-gray-800">{{ formatHours(logs.data?.total_hours) }}</span>
      </p>
    </div>

    <div
      v-if="userInfo.data && !userInfo.data.can_log_time"
      class="mb-3 rounded-lg border border-orange-200 bg-orange-50 px-3 py-2 text-xs text-orange-800"
    >
      ⚠️ No active Employee record is linked to your user, so you cannot log time. Ask HR to set
      "User ID" on your Employee record.
    </div>

    <!-- log form -->
    <form
      class="rounded-lg border border-gray-200 bg-gray-50 p-3"
      @submit.prevent="submitLog"
    >
      <div class="grid grid-cols-2 gap-2">
        <div>
          <label class="text-[10px] font-medium uppercase tracking-wide text-gray-400">Hours</label>
          <input
            v-model="hours"
            type="number"
            min="0.25"
            step="0.25"
            placeholder="1.5"
            class="mt-0.5 w-full rounded-md border-gray-300 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            required
          />
        </div>
        <div>
          <label class="text-[10px] font-medium uppercase tracking-wide text-gray-400">Activity</label>
          <select
            v-model="activityType"
            class="mt-0.5 w-full rounded-md border-gray-300 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            required
          >
            <option value="" disabled>Select…</option>
            <option v-for="activity in activityTypes.data || []" :key="activity" :value="activity">
              {{ activity }}
            </option>
          </select>
        </div>
        <div>
          <label class="text-[10px] font-medium uppercase tracking-wide text-gray-400">
            Start (optional, defaults to now)
          </label>
          <input
            v-model="fromTime"
            type="datetime-local"
            class="mt-0.5 w-full rounded-md border-gray-300 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label class="text-[10px] font-medium uppercase tracking-wide text-gray-400">Note</label>
          <input
            v-model="description"
            type="text"
            placeholder="What did you work on?"
            class="mt-0.5 w-full rounded-md border-gray-300 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500"
          />
        </div>
      </div>
      <div class="mt-2 flex justify-end">
        <Button
          variant="solid"
          type="submit"
          :loading="logTime.loading"
          :disabled="userInfo.data && !userInfo.data.can_log_time"
        >
          Log time
        </Button>
      </div>
    </form>

    <!-- log list -->
    <div v-if="logs.loading && !logs.data" class="py-6 text-center text-sm text-gray-500">
      Loading time logs…
    </div>
    <p v-else-if="!logs.data?.logs?.length" class="py-6 text-center text-sm text-gray-400">
      No time logged yet.
    </p>
    <ul v-else class="mt-3 space-y-1.5">
      <li
        v-for="log in logs.data.logs"
        :key="log.name"
        class="flex items-center gap-2 rounded-md border border-gray-200 px-3 py-2 text-sm"
      >
        <span
          class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-[10px] font-semibold text-indigo-700"
          :title="log.employee_name || log.employee"
        >
          {{ initials(log.employee_name || log.employee) }}
        </span>
        <div class="min-w-0 flex-1">
          <p class="truncate text-gray-800">
            {{ log.activity_type }}<span v-if="log.description" class="text-gray-500"> — {{ log.description }}</span>
          </p>
          <p class="text-[11px] text-gray-400">
            {{ formatDateTime(log.from_time) }} · {{ log.parent }}
          </p>
        </div>
        <span class="shrink-0 text-sm font-semibold text-gray-900">{{ formatHours(log.hours) }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { Button, createResource } from 'frappe-ui'
import { userInfo } from '@/data/session'
import { formatDateTime, formatHours, initials } from '@/utils/format'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  task: { type: String, required: true },
})

const emit = defineEmits(['logged'])

const logs = createResource({
  url: 'agile_projects.api.get_task_timesheets',
})

const activityTypes = createResource({
  url: 'agile_projects.api.get_activity_types',
  cache: 'agile:activity_types',
})

watch(
  () => props.task,
  (task) => {
    if (task) logs.submit({ task })
  },
  { immediate: true }
)

onMounted(() => {
  if (!activityTypes.data && !activityTypes.loading) activityTypes.fetch()
  if (!userInfo.data && !userInfo.loading) userInfo.fetch()
})

const hours = ref('')
const activityType = ref('')
const fromTime = ref('')
const description = ref('')

const logTime = createResource({ url: 'agile_projects.api.log_time' })

function submitLog() {
  if (!activityType.value) {
    toast({ title: 'Pick an activity type', type: 'warning' })
    return
  }
  logTime
    .submit({
      task: props.task,
      hours: hours.value,
      activity_type: activityType.value,
      description: description.value || null,
      from_time: fromTime.value ? fromTime.value.replace('T', ' ') + ':00' : null,
    })
    .then(() => {
      toast({ title: `Logged ${hours.value}h`, type: 'success', timeout: 2500 })
      hours.value = ''
      description.value = ''
      fromTime.value = ''
      logs.submit({ task: props.task })
      emit('logged')
    })
    .catch((err) => {
      toast({ title: 'Could not log time', text: errorMessage(err), type: 'error', timeout: 8000 })
    })
}
</script>
