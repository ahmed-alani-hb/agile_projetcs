<template>
  <div>
    <div class="mb-3 flex items-center justify-between">
      <div>
        <p class="text-sm font-semibold text-gray-900">ERP Module Readiness</p>
        <p class="text-xs text-gray-500">
          {{ signedOff }} of {{ rows.length }} modules signed off
        </p>
      </div>
      <div class="h-1.5 w-28 overflow-hidden rounded-full bg-gray-200">
        <div
          class="h-full rounded-full bg-green-500 transition-all"
          :style="{ width: (rows.length ? (signedOff / rows.length) * 100 : 0) + '%' }"
        ></div>
      </div>
    </div>

    <div v-if="checklist.loading && !rows.length" class="py-8 text-center text-sm text-gray-500">
      Loading checklist…
    </div>

    <p v-else-if="!rows.length" class="rounded-lg border border-dashed border-gray-300 py-8 text-center text-sm text-gray-500">
      {{ readonly ? 'No modules were tracked here.' : 'No modules tracked yet. Add the first one below.' }}
    </p>

    <ul v-else class="space-y-2">
      <li
        v-for="row in rows"
        :key="row.name"
        class="rounded-lg border p-3"
        :class="row.functional_signoff ? 'border-green-200 bg-green-50/50' : 'border-gray-200 bg-white'"
      >
        <div class="flex items-center gap-2">
          <label class="flex items-center gap-2" :class="readonly ? '' : 'cursor-pointer'">
            <input
              type="checkbox"
              class="h-4 w-4 rounded border-gray-300 text-green-600 focus:ring-green-500 disabled:opacity-60"
              :checked="!!row.functional_signoff"
              :disabled="readonly"
              @change="updateRow(row, 'functional_signoff', $event.target.checked ? 1 : 0)"
            />
            <span class="text-sm font-medium text-gray-900">{{ row.module_name }}</span>
          </label>
          <span
            class="rounded-full px-2 py-0.5 text-[11px] font-medium"
            :class="PLATFORM_COLORS[row.system_platform] || 'bg-gray-100 text-gray-600'"
          >
            {{ row.system_platform }}
          </span>
          <span v-if="row.functional_signoff" class="text-[11px] font-medium text-green-700">
            Signed off
          </span>
          <span class="flex-1"></span>
          <button
            v-if="!readonly"
            class="text-xs text-gray-400 hover:text-red-600"
            title="Remove module"
            @click="removeRow(row)"
          >
            ✕
          </button>
        </div>
        <div class="mt-2 grid grid-cols-2 gap-2">
          <div>
            <label class="text-[10px] font-medium uppercase tracking-wide text-gray-400">
              Configuration
            </label>
            <select
              :value="row.configuration_status"
              class="mt-0.5 w-full rounded-md border-gray-300 py-1 text-xs focus:border-indigo-500 focus:ring-indigo-500 disabled:bg-gray-50 disabled:text-gray-500"
              :disabled="readonly"
              @change="updateRow(row, 'configuration_status', $event.target.value)"
            >
              <option v-for="status in CONFIG_STATUSES" :key="status" :value="status">
                {{ status }}
              </option>
            </select>
          </div>
          <div>
            <label class="text-[10px] font-medium uppercase tracking-wide text-gray-400">
              Data Migration
            </label>
            <select
              :value="row.data_migration_status"
              class="mt-0.5 w-full rounded-md border-gray-300 py-1 text-xs focus:border-indigo-500 focus:ring-indigo-500 disabled:bg-gray-50 disabled:text-gray-500"
              :disabled="readonly"
              @change="updateRow(row, 'data_migration_status', $event.target.value)"
            >
              <option v-for="status in MIGRATION_STATUSES" :key="status" :value="status">
                {{ status }}
              </option>
            </select>
          </div>
        </div>
      </li>
    </ul>

    <!-- add row -->
    <form v-if="!readonly" class="mt-3 flex items-end gap-2" @submit.prevent="addRow">
      <div class="flex-1">
        <label class="text-[10px] font-medium uppercase tracking-wide text-gray-400">Module</label>
        <select
          v-model="newModule"
          class="mt-0.5 w-full rounded-md border-gray-300 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500"
        >
          <option v-for="moduleName in MODULES" :key="moduleName" :value="moduleName">
            {{ moduleName }}
          </option>
        </select>
      </div>
      <div class="flex-1">
        <label class="text-[10px] font-medium uppercase tracking-wide text-gray-400">Platform</label>
        <select
          v-model="newPlatform"
          class="mt-0.5 w-full rounded-md border-gray-300 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500"
        >
          <option v-for="platform in PLATFORMS" :key="platform" :value="platform">
            {{ platform }}
          </option>
        </select>
      </div>
      <Button variant="subtle" :loading="addResource.loading" type="submit">Add</Button>
    </form>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Button, createResource } from 'frappe-ui'
import {
  MODULES,
  PLATFORMS,
  PLATFORM_COLORS,
  CONFIG_STATUSES,
  MIGRATION_STATUSES,
} from '@/utils/statuses'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  project: { type: String, required: true },
  // Superseded by the Agile Module doctype; frozen for one release so the
  // checklist -> modules migration has a visible rollback path.
  readonly: { type: Boolean, default: false },
})

const emit = defineEmits(['progress'])

const rows = ref([])

const checklist = createResource({
  url: 'agile_projects.api.get_checklist',
  onSuccess(data) {
    rows.value = data.rows || []
  },
  onError(err) {
    toast({ title: 'Failed to load checklist', text: errorMessage(err), type: 'error' })
  },
})

watch(
  () => props.project,
  (project) => {
    if (project) checklist.submit({ project })
  },
  { immediate: true }
)

const signedOff = computed(() => rows.value.filter((row) => row.functional_signoff).length)

const updateResource = createResource({ url: 'agile_projects.api.update_checklist_row' })

function updateRow(row, field, value) {
  if (props.readonly) return
  const previous = row[field]
  row[field] = value
  updateResource
    .submit({ project: props.project, row_name: row.name, fields: { [field]: value } })
    .then((data) => {
      Object.assign(row, data.row)
      emit('progress', data.percent_complete)
    })
    .catch((err) => {
      row[field] = previous
      toast({ title: 'Could not update checklist', text: errorMessage(err), type: 'error' })
    })
}

const addResource = createResource({ url: 'agile_projects.api.add_checklist_row' })
const newModule = ref(MODULES[0])
const newPlatform = ref('ERPNext')

function addRow() {
  addResource
    .submit({
      project: props.project,
      module_name: newModule.value,
      system_platform: newPlatform.value,
    })
    .then((data) => {
      rows.value.push(data.row)
      emit('progress', data.percent_complete)
    })
    .catch((err) => {
      toast({ title: 'Could not add module', text: errorMessage(err), type: 'error' })
    })
}

const deleteResource = createResource({ url: 'agile_projects.api.delete_checklist_row' })

function removeRow(row) {
  if (!window.confirm(`Remove ${row.module_name} from the checklist?`)) return
  deleteResource
    .submit({ project: props.project, row_name: row.name })
    .then((data) => {
      rows.value = rows.value.filter((r) => r.name !== row.name)
      emit('progress', data.percent_complete)
    })
    .catch((err) => {
      toast({ title: 'Could not remove module', text: errorMessage(err), type: 'error' })
    })
}
</script>
