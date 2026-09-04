<template>
  <Autocomplete
    :options="options"
    :model-value="selectedOption"
    :placeholder="placeholder"
    @update:model-value="onSelect"
  />
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { Autocomplete, createResource } from 'frappe-ui'

const props = defineProps({
  modelValue: { type: String, default: null },
  placeholder: { type: String, default: 'Assign SME' },
})

const emit = defineEmits(['update:modelValue'])

const employees = createResource({
  url: 'agile_projects.api.get_employees',
  cache: 'agile:employees',
})

onMounted(() => {
  if (!employees.data && !employees.loading) {
    employees.fetch()
  }
})

const options = computed(() => {
  const list = (employees.data || []).map((employee) => ({
    label: employee.designation
      ? `${employee.employee_name} · ${employee.designation}`
      : employee.employee_name,
    value: employee.name,
  }))
  return [{ label: 'Unassigned', value: '' }, ...list]
})

const selectedOption = computed(
  () => options.value.find((option) => option.value === (props.modelValue || '')) || null
)

function onSelect(option) {
  const value = option && typeof option === 'object' ? option.value : option
  emit('update:modelValue', value || null)
}
</script>
