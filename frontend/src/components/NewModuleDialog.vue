<template>
  <Dialog
    :model-value="modelValue"
    :options="{ title: 'Add module' }"
    @update:model-value="(value) => emit('update:modelValue', value)"
  >
    <template #body-content>
      <form class="space-y-4" @submit.prevent="submit">
        <div>
          <label class="text-xs font-medium text-gray-500">Module</label>
          <select
            v-model="form.module_name"
            required
            class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
          >
            <option value="" disabled>Choose a module…</option>
            <option v-for="module in MODULES" :key="module" :value="module">{{ module }}</option>
          </select>
        </div>

        <div>
          <label class="text-xs font-medium text-gray-500">System Platform</label>
          <select
            v-model="form.system_platform"
            required
            class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
          >
            <option v-for="platform in PLATFORMS" :key="platform" :value="platform">
              {{ platform }}
            </option>
          </select>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="text-xs font-medium text-gray-500">SME Responsible</label>
            <div class="mt-1">
              <EmployeePicker v-model="form.sme_responsible" />
            </div>
          </div>
          <div>
            <label class="text-xs font-medium text-gray-500">Target Go-Live</label>
            <input
              v-model="form.target_go_live"
              type="date"
              class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            />
          </div>
        </div>

        <p class="text-[11px] text-gray-400">
          New modules start at the <span class="font-medium">Configure</span> gate.
        </p>

        <div class="flex justify-end gap-2 pt-1">
          <Button variant="subtle" type="button" @click="emit('update:modelValue', false)">
            Cancel
          </Button>
          <Button variant="solid" type="submit" :loading="create.loading">Add module</Button>
        </div>
      </form>
    </template>
  </Dialog>
</template>

<script setup>
import { reactive, watch } from 'vue'
import { Button, Dialog, createResource } from 'frappe-ui'
import EmployeePicker from './EmployeePicker.vue'
import { MODULES, PLATFORMS } from '@/utils/statuses'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  project: { type: String, required: true },
})

const emit = defineEmits(['update:modelValue', 'created'])

const form = reactive({
  module_name: '',
  system_platform: 'ERPNext',
  sme_responsible: null,
  target_go_live: '',
})

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      form.module_name = ''
      form.system_platform = 'ERPNext'
      form.sme_responsible = null
      form.target_go_live = ''
    }
  }
)

const create = createResource({ url: 'agile_projects.modules.create_module' })

function submit() {
  if (!form.module_name) return
  create
    .submit({
      project: props.project,
      module_name: form.module_name,
      system_platform: form.system_platform,
      sme_responsible: form.sme_responsible,
      target_go_live: form.target_go_live || null,
    })
    .then(() => {
      toast({ title: 'Module added', type: 'success', timeout: 2000 })
      emit('created')
    })
    .catch((err) => {
      // The commonest rejection is the one-module-per-project rule.
      toast({ title: 'Could not add module', text: errorMessage(err), type: 'error' })
    })
}
</script>
