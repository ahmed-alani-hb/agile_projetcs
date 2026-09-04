<template>
  <div class="flex h-full w-72 shrink-0 flex-col rounded-xl border-t-4 bg-gray-100" :class="meta.column">
    <div class="flex items-center gap-2 px-3 pb-1 pt-3">
      <span class="h-2 w-2 rounded-full" :class="meta.dot"></span>
      <span class="text-sm font-semibold text-gray-800">{{ columnKey }}</span>
      <span class="rounded-full bg-white px-1.5 py-0.5 text-[11px] font-medium text-gray-500">
        {{ visibleItems.length }}
      </span>
      <span class="flex-1"></span>
      <span v-if="statLabel" class="text-[11px] font-medium text-gray-400" :title="statTitle">
        {{ statLabel }}
      </span>
    </div>

    <draggable
      :list="items"
      :group="group"
      item-key="name"
      class="thin-scrollbar flex flex-1 flex-col gap-2 overflow-y-auto p-2"
      :animation="150"
      ghost-class="opacity-40"
      @change="(evt) => $emit('card-moved', evt, columnKey)"
    >
      <template #item="{ element }">
        <div v-show="isVisible(element)">
          <!-- `open-task` is the generic "open this card's document" emit; the
               gate board reuses it for modules. -->
          <slot name="card" :item="element" :open="() => $emit('open-task', element)">
            <TaskCard :task="element" @open="$emit('open-task', element)" />
          </slot>
        </div>
      </template>
    </draggable>

    <div v-if="canAdd" class="p-2 pt-0">
      <form v-if="adding" @submit.prevent="submitQuickAdd">
        <input
          ref="quickAddInput"
          v-model="newSubject"
          type="text"
          :placeholder="addPlaceholder"
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
        {{ addLabel }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import draggable from 'vuedraggable'
import TaskCard from './TaskCard.vue'
import { STATUS_META } from '@/utils/statuses'

// Shared by the task board and the module gate board. Every prop below the
// first two defaults to the task board's original behaviour, so BoardView.vue
// needs no changes and the shipped board has no new surface to regress.
const props = defineProps({
  column: { type: Object, required: true },
  isVisible: { type: Function, default: () => true },
  // Which key on `column` names the column, and which holds its cards.
  keyField: { type: String, default: 'status' },
  itemsKey: { type: String, default: 'tasks' },
  // Column colours: a map keyed like `columnKey`, plus the key to fall back to.
  metaMap: { type: Object, default: () => STATUS_META },
  fallbackMetaKey: { type: String, default: 'Backlog' },
  // Drag scope. Two boards mounted at once would trade cards on a shared name.
  group: { type: String, default: 'tasks' },
  // Right-hand column stat. Receives the visible cards; return null to hide.
  stat: { type: Function, default: null },
  statTitle: { type: String, default: 'Total complexity points' },
  canAdd: { type: Boolean, default: true },
  addLabel: { type: String, default: '+ Add task' },
  addPlaceholder: { type: String, default: 'Task subject — press Enter' },
})

const emit = defineEmits(['card-moved', 'open-task', 'quick-add'])

const columnKey = computed(() => props.column[props.keyField])

const items = computed(() => props.column[props.itemsKey] || [])

const meta = computed(
  () => props.metaMap[columnKey.value] || props.metaMap[props.fallbackMetaKey] || {}
)

const visibleItems = computed(() => items.value.filter((item) => props.isVisible(item)))

const statLabel = computed(() => {
  if (props.stat) return props.stat(visibleItems.value)
  const points = visibleItems.value.reduce(
    (sum, task) => sum + (parseInt(task.complexity_points) || 0),
    0
  )
  return points ? `${points} pts` : null
})

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
    emit('quick-add', columnKey.value, subject)
  }
  cancelQuickAdd()
}
</script>
