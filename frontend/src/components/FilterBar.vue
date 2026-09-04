<template>
  <div class="flex flex-wrap items-center gap-2">
    <input
      :value="modelValue.search"
      type="text"
      placeholder="Search tasks…"
      class="w-44 rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
      @input="update('search', $event.target.value)"
    />

    <select
      :value="modelValue.status || ''"
      class="rounded-md border-gray-300 text-sm text-gray-700 focus:border-indigo-500 focus:ring-indigo-500"
      @change="update('status', $event.target.value || null)"
    >
      <option value="">All statuses</option>
      <option v-for="status in STATUSES" :key="status" :value="status">{{ status }}</option>
    </select>

    <select
      :value="modelValue.sme_responsible || ''"
      class="rounded-md border-gray-300 text-sm text-gray-700 focus:border-indigo-500 focus:ring-indigo-500"
      @change="update('sme_responsible', $event.target.value || null)"
    >
      <option value="">All SMEs</option>
      <option v-for="employee in employees.data || []" :key="employee.name" :value="employee.name">
        {{ employee.employee_name }}
      </option>
    </select>

    <select
      :value="modelValue.priority || ''"
      class="rounded-md border-gray-300 text-sm text-gray-700 focus:border-indigo-500 focus:ring-indigo-500"
      @change="update('priority', $event.target.value || null)"
    >
      <option value="">All priorities</option>
      <option v-for="priority in PRIORITIES" :key="priority" :value="priority">
        {{ priority }}
      </option>
    </select>

    <label class="flex cursor-pointer items-center gap-1.5 text-sm text-gray-600">
      <input
        type="checkbox"
        class="h-3.5 w-3.5 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
        :checked="!!modelValue.overdue"
        @change="update('overdue', $event.target.checked ? 1 : null)"
      />
      Overdue
    </label>

    <button
      v-if="hasFilters"
      class="text-xs text-gray-500 underline hover:text-gray-700"
      @click="$emit('update:modelValue', {})"
    >
      Clear
    </button>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { createResource } from 'frappe-ui'
import { STATUSES, PRIORITIES } from '@/utils/statuses'

const props = defineProps({
  modelValue: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['update:modelValue'])

const employees = createResource({
  url: 'agile_projects.api.get_employees',
  cache: 'agile:employees',
})

onMounted(() => {
  if (!employees.data && !employees.loading) employees.fetch()
})

const hasFilters = computed(() =>
  Object.values(props.modelValue || {}).some((v) => v !== null && v !== '' && v !== undefined)
)

function update(key, value) {
  const next = { ...props.modelValue }
  if (value === null || value === '') {
    delete next[key]
  } else {
    next[key] = value
  }
  emit('update:modelValue', next)
}
</script>
