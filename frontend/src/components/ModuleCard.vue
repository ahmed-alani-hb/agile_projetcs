<template>
  <div
    class="cursor-pointer rounded-lg border border-gray-200 bg-white p-3 shadow-sm transition hover:shadow-md"
    :class="{ 'ring-1 ring-red-300': module.blocked_tasks > 0 }"
    @click="$emit('open')"
  >
    <div class="flex items-start gap-2">
      <p class="min-w-0 flex-1 text-sm font-medium leading-snug text-gray-900">
        {{ module.module_name }}
      </p>
      <span
        class="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold"
        :class="PLATFORM_COLORS[module.system_platform] || 'bg-gray-100 text-gray-600'"
      >
        {{ module.system_platform }}
      </span>
    </div>

    <!-- task rollup -->
    <div class="mt-2.5">
      <div class="flex items-center justify-between text-[11px] text-gray-500">
        <span>{{ module.done_tasks }}/{{ module.total_tasks }} tasks</span>
        <span class="font-medium">{{ Math.round(module.task_progress || 0) }}%</span>
      </div>
      <div class="mt-1 h-1.5 overflow-hidden rounded-full bg-gray-200">
        <div
          class="h-full rounded-full transition-all"
          :class="module.task_progress >= 100 ? 'bg-green-500' : 'bg-indigo-500'"
          :style="{ width: Math.min(module.task_progress || 0, 100) + '%' }"
        ></div>
      </div>
    </div>

    <!-- readiness chips: the two statuses the gates actually key on -->
    <div class="mt-2.5 flex flex-wrap items-center gap-1">
      <span
        class="rounded px-1.5 py-0.5 text-[10px]"
        :class="READINESS_COLORS[module.configuration_status] || 'bg-gray-100 text-gray-600'"
        title="Configuration status"
      >
        C: {{ module.configuration_status || 'Not Started' }}
      </span>
      <span
        class="rounded px-1.5 py-0.5 text-[10px]"
        :class="READINESS_COLORS[module.data_migration_status] || 'bg-gray-100 text-gray-600'"
        title="Data migration status"
      >
        M: {{ module.data_migration_status || 'Not Started' }}
      </span>
      <span
        v-if="module.functional_signoff"
        class="rounded bg-green-100 px-1.5 py-0.5 text-[10px] font-medium text-green-700"
        title="Functional sign-off received"
      >
        ✓ Signed off
      </span>
    </div>

    <!-- advisory, never a gate: blocked tasks fire too often to refuse a move -->
    <p
      v-if="module.blocked_tasks"
      class="mt-2 rounded bg-red-50 px-2 py-1 text-[11px] font-medium text-red-700"
    >
      {{ module.blocked_tasks }} blocked task{{ module.blocked_tasks === 1 ? '' : 's' }}
    </p>

    <div class="mt-2.5 flex items-center gap-2 border-t border-gray-100 pt-2">
      <span
        v-if="module.target_go_live"
        class="text-[11px]"
        :class="goLiveLate ? 'font-medium text-red-600' : 'text-gray-500'"
        :title="'Target go-live ' + module.target_go_live"
      >
        🏁 {{ formatDate(module.target_go_live) }}
      </span>
      <span class="flex-1"></span>
      <span
        v-if="module.sme_responsible"
        class="flex h-5 w-5 items-center justify-center rounded-full bg-indigo-100 text-[9px] font-semibold text-indigo-700"
        :title="module.sme_name || module.sme_responsible"
      >
        {{ initials(module.sme_name || module.sme_responsible) }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { PLATFORM_COLORS } from '@/utils/statuses'
import { formatDate, initials, isOverdue } from '@/utils/format'

const props = defineProps({
  module: { type: Object, required: true },
})

defineEmits(['open'])

const READINESS_COLORS = {
  'Not Started': 'bg-gray-100 text-gray-600',
  'In Progress': 'bg-orange-100 text-orange-700',
  Configured: 'bg-blue-100 text-blue-700',
  Verified: 'bg-green-100 text-green-700',
  Migrated: 'bg-blue-100 text-blue-700',
  Validated: 'bg-green-100 text-green-700',
}

const goLiveLate = computed(
  () => props.module.gate !== 'Live' && isOverdue(props.module.target_go_live)
)
</script>
