<template>
  <Dialog
    :model-value="modelValue"
    :options="{ title: 'New Task', size: 'xl' }"
    @update:model-value="(value) => emit('update:modelValue', value)"
  >
    <template #body-content>
      <form class="space-y-4" @submit.prevent="create">
        <div>
          <label class="text-xs font-medium text-gray-500">Subject *</label>
          <input
            ref="subjectInput"
            v-model="subject"
            type="text"
            placeholder="What needs to be done?"
            class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            required
          />
        </div>
        <div>
          <label class="text-xs font-medium text-gray-500">Description</label>
          <textarea
            v-model="description"
            rows="3"
            class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
          ></textarea>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="text-xs font-medium text-gray-500">Status</label>
            <select
              v-model="status"
              class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            >
              <option v-for="s in STATUSES" :key="s" :value="s">{{ s }}</option>
            </select>
          </div>
          <div>
            <label class="text-xs font-medium text-gray-500">Priority</label>
            <select
              v-model="priority"
              class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            >
              <option v-for="p in PRIORITIES" :key="p" :value="p">{{ p }}</option>
            </select>
          </div>
          <div>
            <label class="text-xs font-medium text-gray-500">Complexity Points</label>
            <select
              v-model="points"
              class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            >
              <option value="">Unestimated</option>
              <option v-for="p in POINT_OPTIONS" :key="p" :value="p">{{ p }} points</option>
            </select>
          </div>
          <div>
            <label class="text-xs font-medium text-gray-500">Due Date</label>
            <input
              v-model="dueDate"
              type="date"
              class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            />
          </div>
        </div>
        <div>
          <label class="text-xs font-medium text-gray-500">SME Responsible</label>
          <div class="mt-1">
            <EmployeePicker v-model="sme" />
          </div>
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <Button variant="subtle" type="button" @click="emit('update:modelValue', false)">
            Cancel
          </Button>
          <Button variant="solid" type="submit" :loading="createTask.loading">Create Task</Button>
        </div>
      </form>
    </template>
  </Dialog>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import { Button, Dialog, createResource } from 'frappe-ui'
import EmployeePicker from './EmployeePicker.vue'
import { STATUSES, POINT_OPTIONS, PRIORITIES } from '@/utils/statuses'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  project: { type: String, required: true },
  defaultStatus: { type: String, default: 'Backlog' },
})

const emit = defineEmits(['update:modelValue', 'created'])

const subject = ref('')
const description = ref('')
const status = ref(props.defaultStatus)
const priority = ref('Medium')
const points = ref('')
const sme = ref(null)
const dueDate = ref('')
const subjectInput = ref(null)

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      subject.value = ''
      description.value = ''
      status.value = props.defaultStatus
      priority.value = 'Medium'
      points.value = ''
      sme.value = null
      dueDate.value = ''
      nextTick(() => subjectInput.value?.focus())
    }
  }
)

const createTask = createResource({ url: 'agile_projects.api.create_task' })

function create() {
  if (!subject.value.trim()) return
  createTask
    .submit({
      project: props.project,
      subject: subject.value.trim(),
      description: description.value || null,
      status: status.value,
      priority: priority.value,
      complexity_points: points.value || null,
      sme_responsible: sme.value || null,
      exp_end_date: dueDate.value || null,
    })
    .then((data) => {
      toast({ title: 'Task created', text: data.name, type: 'success', timeout: 2500 })
      emit('created', data)
    })
    .catch((err) => {
      toast({ title: 'Could not create task', text: errorMessage(err), type: 'error' })
    })
}
</script>
