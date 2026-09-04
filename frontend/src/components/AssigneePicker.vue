<template>
  <div>
    <div v-if="assignees.length" class="mb-1.5 flex flex-wrap gap-1">
      <span
        v-for="person in assignees"
        :key="person.user"
        class="flex items-center gap-1 rounded-full bg-gray-100 py-0.5 pl-0.5 pr-1.5 text-[11px] text-gray-700"
      >
        <img
          v-if="person.user_image"
          :src="person.user_image"
          :alt="person.user_name"
          class="h-4 w-4 rounded-full object-cover"
        />
        <span
          v-else
          class="flex h-4 w-4 items-center justify-center rounded-full bg-indigo-100 text-[8px] font-semibold text-indigo-700"
        >
          {{ initials(person.user_name) }}
        </span>
        {{ person.user_name }}
        <button
          class="ml-0.5 text-gray-400 hover:text-red-600"
          :title="`Unassign ${person.user_name}`"
          @click="unassign(person)"
        >
          ✕
        </button>
      </span>
    </div>

    <Autocomplete
      :options="options"
      :model-value="null"
      placeholder="Assign someone…"
      @update:model-value="onSelect"
    />
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { Autocomplete, createResource } from 'frappe-ui'
import { initials } from '@/utils/format'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  task: { type: String, required: true },
  assignees: { type: Array, default: () => [] },
})

const emit = defineEmits(['changed'])

// The same cached list EmployeePicker uses; filtered to people who have a
// login, since an assignment without a User is a dead end.
const employees = createResource({
  url: 'agile_projects.api.get_employees',
  cache: 'agile:employees',
})

onMounted(() => {
  if (!employees.data && !employees.loading) employees.fetch()
})

const options = computed(() => {
  const taken = new Set(props.assignees.map((person) => person.user))
  return (employees.data || [])
    .filter((employee) => employee.user_id && !taken.has(employee.user_id))
    .map((employee) => ({
      label: employee.designation
        ? `${employee.employee_name} · ${employee.designation}`
        : employee.employee_name,
      value: employee.user_id,
    }))
})

const assign = createResource({ url: 'agile_projects.collaboration.assign_task' })
const unassignResource = createResource({ url: 'agile_projects.collaboration.unassign_task' })

function onSelect(value) {
  const user = value && typeof value === 'object' ? value.value : value
  if (!user) return
  assign
    .submit({ task: props.task, users: [user] })
    .then((data) => {
      // The server refuses to assign someone who cannot read the task, rather
      // than creating a notification into a document they cannot open.
      if (data.skipped?.length) {
        toast({
          title: 'Not assigned',
          text: `${data.skipped.join(', ')} cannot access this task.`,
          type: 'warning',
          timeout: 8000,
        })
      }
      emit('changed', data.assignees)
    })
    .catch((err) => {
      toast({ title: 'Could not assign', text: errorMessage(err), type: 'error' })
    })
}

function unassign(person) {
  unassignResource
    .submit({ task: props.task, user: person.user })
    .then((data) => emit('changed', data.assignees))
    .catch((err) => {
      toast({ title: 'Could not unassign', text: errorMessage(err), type: 'error' })
    })
}
</script>
