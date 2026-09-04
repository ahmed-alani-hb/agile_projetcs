<template>
  <div class="flex h-full w-72 shrink-0 flex-col rounded-xl border-t-4 bg-gray-100" :class="meta.column">
    <div class="flex items-center gap-2 px-3 pb-1 pt-3">
      <span class="h-2 w-2 rounded-full" :class="meta.dot"></span>
      <span class="text-sm font-semibold text-gray-800">{{ column.status }}</span>
      <span class="rounded-full bg-white px-1.5 py-0.5 text-[11px] font-medium text-gray-500">
        {{ visibleTasks.length }}
      </span>
      <span class="flex-1"></span>
      <span v-if="totalPoints" class="text-[11px] font-medium text-gray-400" title="Total complexity points">
        {{ totalPoints }} pts
      </span>
    </div>

    <draggable
      :list="column.tasks"
      group="tasks"
      item-key="name"
      class="thin-scrollbar flex flex-1 flex-col gap-2 overflow-y-auto p-2"
      :animation="150"
      ghost-class="opacity-40"
      @change="(evt) => $emit('card-moved', evt, column.status)"
    >
      <template #item="{ element }">
        <div v-show="isVisible(element)">
          <TaskCard :task="element" @open="$emit('open-task', element)" />
        </div>
      </template>
    </draggable>

    <div class="p-2 pt-0">
      <form v-if="adding" @submit.prevent="submitQuickAdd">
        <input
          ref="quickAddInput"
          v-model="newSubject"
          type="text"
          placeholder="Task subject — press Enter"
          class="w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
          @keydown.esc="cancelQuickAdd"
          @blur="cancelQuickAdd"
        />
      </form>
      <button
        v-else
        class="w-full rounded-md px-2 py-1.5 text-left text-sm text-gray-500 hover:bg-gray-200 hover:text-gray-700"
        @click="startQuickAdd"
      >
        + Add task
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import draggable from 'vuedraggable'
import TaskCard from './TaskCard.vue'
import { STATUS_META } from '@/utils/statuses'

const props = defineProps({
  column: { type: Object, required: true },
  isVisible: { type: Function, default: () => true },
})

const emit = defineEmits(['card-moved', 'open-task', 'quick-add'])

const meta = computed(() => STATUS_META[props.column.status] || STATUS_META.Backlog)

const visibleTasks = computed(() => props.column.tasks.filter((task) => props.isVisible(task)))

const totalPoints = computed(() =>
  visibleTasks.value.reduce((sum, task) => sum + (parseInt(task.complexity_points) || 0), 0)
)

const adding = ref(false)
const newSubject = ref('')
const quickAddInput = ref(null)

function startQuickAdd() {
  adding.value = true
  nextTick(() => quickAddInput.value?.focus())
}

function cancelQuickAdd() {
  adding.value = false
  newSubject.value = ''
}

function submitQuickAdd() {
  const subject = newSubject.value.trim()
  if (subject) {
    emit('quick-add', props.column.status, subject)
  }
  cancelQuickAdd()
}
</script>
