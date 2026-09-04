<template>
  <Dialog
    :model-value="modelValue"
    :options="{ title: 'Add cutover step', size: 'xl' }"
    @update:model-value="(value) => emit('update:modelValue', value)"
  >
    <template #body-content>
      <form class="space-y-4" @submit.prevent="submit">
        <div>
          <label class="text-xs font-medium text-gray-500">Title *</label>
          <input
            v-model="form.title"
            type="text"
            required
            placeholder="e.g. Freeze the legacy system"
            class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
          />
        </div>

        <div>
          <label class="text-xs font-medium text-gray-500">Description</label>
          <textarea
            v-model="form.description"
            rows="3"
            placeholder="What exactly has to happen, and how do we know it worked?"
            class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
          ></textarea>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="text-xs font-medium text-gray-500">Module</label>
            <select
              v-model="form.agile_module"
              class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            >
              <option :value="null">None</option>
              <option v-for="module in modules.data || []" :key="module.name" :value="module.name">
                {{ module.module_name }}
              </option>
            </select>
          </div>
          <div>
            <label class="text-xs font-medium text-gray-500">Owner</label>
            <div class="mt-1">
              <EmployeePicker v-model="form.owner_employee" />
            </div>
          </div>
          <div class="col-span-2">
            <label class="text-xs font-medium text-gray-500">Depends on</label>
            <select
              v-model="form.depends_on"
              class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            >
              <option :value="null">Nothing — can run at any time</option>
              <option v-for="step in steps" :key="step.name" :value="step.name">
                {{ step.title }}
              </option>
            </select>
            <p class="mt-1 text-[11px] text-gray-400">
              Enforced on completion, not on start — a step can be prepared early.
            </p>
          </div>
          <div>
            <label class="text-xs font-medium text-gray-500">Planned start</label>
            <input
              v-model="form.planned_start"
              type="datetime-local"
              class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label class="text-xs font-medium text-gray-500">Planned end</label>
            <input
              v-model="form.planned_end"
              type="datetime-local"
              class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            />
          </div>
        </div>

        <div class="flex justify-end gap-2 pt-1">
          <Button variant="subtle" type="button" @click="emit('update:modelValue', false)">
            Cancel
          </Button>
          <Button variant="solid" type="submit" :loading="create.loading">Add step</Button>
        </div>
      </form>
    </template>
  </Dialog>
</template>

<script setup>
import { reactive, watch } from 'vue'
import { Button, Dialog, createResource } from 'frappe-ui'
import EmployeePicker from './EmployeePicker.vue'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  project: { type: String, required: true },
  // Existing steps, so a new one can depend on any of them.
  steps: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'created'])

const form = reactive({
  title: '',
  description: '',
  agile_module: null,
  owner_employee: null,
  depends_on: null,
  planned_start: '',
  planned_end: '',
})

const modules = createResource({
  url: 'agile_projects.modules.get_modules',
  makeParams: () => ({ project: props.project }),
  // The dialog needs a flat list; the endpoint returns gate columns.
  transform: (data) => (data.columns || []).flatMap((column) => column.modules),
})

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    form.title = ''
    form.description = ''
    form.agile_module = null
    form.owner_employee = null
    form.depends_on = null
    form.planned_start = ''
    form.planned_end = ''
    modules.reload()
  }
)

const create = createResource({ url: 'agile_projects.modules.add_cutover_step' })

// <input type="datetime-local"> yields "YYYY-MM-DDTHH:MM"; Frappe stores
// "YYYY-MM-DD HH:MM:SS".
function toFrappeDatetime(value) {
  if (!value) return null
  return `${value.replace('T', ' ')}:00`
}

function submit() {
  if (!form.title.trim()) return
  create
    .submit({
      project: props.project,
      title: form.title.trim(),
      description: form.description || null,
      agile_module: form.agile_module,
      owner_employee: form.owner_employee,
      depends_on: form.depends_on,
      planned_start: toFrappeDatetime(form.planned_start),
      planned_end: toFrappeDatetime(form.planned_end),
    })
    .then(() => {
      toast({ title: 'Step added', type: 'success', timeout: 2000 })
      emit('created')
    })
    .catch((err) => {
      toast({ title: 'Could not add step', text: errorMessage(err), type: 'error' })
    })
}
</script>
