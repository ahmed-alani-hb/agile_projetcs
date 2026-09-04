<template>
  <div
    class="cursor-pointer select-none rounded-lg border border-gray-200 bg-white p-3 shadow-sm transition hover:border-indigo-300 hover:shadow"
    :class="{ 'border-red-300 ring-1 ring-red-200': task.is_blocked }"
    @click="$emit('open')"
  >
    <div class="flex items-center justify-between gap-2">
      <span class="truncate font-mono text-[11px] text-gray-400">{{ task.name }}</span>
      <span
        v-if="task.priority"
        class="shrink-0 text-[11px] font-medium"
        :class="PRIORITY_COLORS[task.priority] || 'text-gray-500'"
      >
        {{ task.priority }}
      </span>
    </div>

    <p class="mt-1 line-clamp-2 text-sm font-medium text-gray-900">{{ task.subject }}</p>

    <div
      v-if="task.is_blocked"
      class="mt-2 flex items-center gap-1.5 rounded-md bg-red-50 px-2 py-1 text-[11px] font-medium text-red-700"
      :title="blockedTooltip"
    >
      <span>⛔</span>
      <span class="truncate">Blocked by {{ openBlockers.length }} task{{ openBlockers.length === 1 ? '' : 's' }}</span>
    </div>

    <div class="mt-2 flex items-center gap-1.5">
      <span
        v-if="task.complexity_points"
        class="rounded-full px-1.5 py-0.5 text-[11px] font-semibold"
        :class="POINT_COLORS[task.complexity_points] || 'bg-gray-100 text-gray-700'"
        title="Complexity points"
      >
        {{ task.complexity_points }} pts
      </span>
      <span
        v-if="task.exp_end_date"
        class="rounded px-1 py-0.5 text-[11px]"
        :class="overdue ? 'font-medium text-red-600' : 'text-gray-500'"
        title="Due date"
      >
        {{ formatDate(task.exp_end_date) }}
      </span>
      <span v-if="parseFloat(task.actual_time)" class="text-[11px] text-gray-400" title="Hours logged">
        {{ formatHours(task.actual_time) }}
      </span>
      <span class="flex-1"></span>
      <!-- assignees first: who is doing it outranks who owns the subject -->
      <span
        v-for="person in (task.assignees || []).slice(0, 3)"
        :key="person.user"
        class="-ml-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gray-200 text-[10px] font-semibold text-gray-700 ring-1 ring-white first:ml-0"
        :title="person.user_name"
      >
        {{ initials(person.user_name) }}
      </span>
      <span
        v-if="(task.assignees || []).length > 3"
        class="-ml-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gray-100 text-[10px] font-medium text-gray-500 ring-1 ring-white"
        :title="`${task.assignees.length} assignees`"
      >
        +{{ task.assignees.length - 3 }}
      </span>
      <span
        v-if="task.sme_responsible"
        class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-[10px] font-semibold text-indigo-700"
        :title="'SME: ' + (task.sme_name || task.sme_responsible)"
      >
        {{ initials(task.sme_name || task.sme_responsible) }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { POINT_COLORS, PRIORITY_COLORS } from '@/utils/statuses'
import { formatDate, formatHours, initials, isOverdue } from '@/utils/format'

const props = defineProps({
  task: { type: Object, required: true },
})

defineEmits(['open'])

const openBlockers = computed(() =>
  (props.task.blocked_by || []).filter((dep) => dep.status !== 'Done')
)

const blockedTooltip = computed(() =>
  openBlockers.value.map((dep) => `${dep.task}: ${dep.subject} (${dep.status})`).join('\n')
)

const overdue = computed(() => props.task.status !== 'Done' && isOverdue(props.task.exp_end_date))
</script>
