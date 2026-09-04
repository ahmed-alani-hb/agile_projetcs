<template>
  <div class="flex items-center gap-0.5 rounded-lg bg-gray-100 p-0.5">
    <button
      v-for="option in views"
      :key="option.value"
      class="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-sm font-medium transition"
      :class="
        modelValue === option.value
          ? 'bg-white text-gray-900 shadow-sm'
          : 'text-gray-500 hover:text-gray-800'
      "
      :title="option.label"
      @click="$emit('update:modelValue', option.value)"
    >
      <span aria-hidden="true">{{ option.icon }}</span>
      <span class="hidden sm:inline">{{ option.label }}</span>
    </button>
  </div>
</template>

<script setup>
defineProps({
  modelValue: { type: String, default: 'board' },
})

defineEmits(['update:modelValue'])

const views = [
  { value: 'board', label: 'Board', icon: '▦' },
  { value: 'list', label: 'List', icon: '☰' },
  { value: 'table', label: 'Table', icon: '⊞' },
  { value: 'timeline', label: 'Timeline', icon: '⇥' },
  { value: 'calendar', label: 'Calendar', icon: '▤' },
  { value: 'sheet', label: 'Sheet', icon: '🔗' },
  { value: 'modules', label: 'Modules', icon: '⛩' },
  { value: 'cutover', label: 'Cutover', icon: '🏁' },
  { value: 'dashboard', label: 'Metrics', icon: '📈' },
]
</script>
