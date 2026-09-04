<template>
  <teleport to="body">
    <transition name="fade">
      <div v-if="modelValue" class="fixed inset-0 z-40 bg-black/30" @click="close"></div>
    </transition>
    <transition name="slide">
      <div
        v-if="modelValue"
        class="fixed inset-y-0 right-0 z-50 flex w-full max-w-lg flex-col bg-white shadow-2xl"
      >
        <!-- header -->
        <div class="flex items-center gap-3 border-b border-gray-200 px-5 py-3">
          <span class="text-sm font-semibold text-gray-900">
            {{ detail?.module_name || 'Module' }}
          </span>
          <span
            v-if="detail"
            class="rounded-full px-2 py-0.5 text-[11px] font-medium"
            :class="gateMeta.pill"
          >
            {{ detail.gate }}
          </span>
          <span class="flex-1"></span>
          <button
            class="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
            @click="close"
          >
            ✕
          </button>
        </div>

        <div class="thin-scrollbar flex-1 overflow-y-auto px-5 py-4">
          <div v-if="!detail" class="py-10 text-center text-sm text-gray-500">Loading module…</div>

          <div v-else class="space-y-5">
            <!-- gate -->
            <div>
              <label class="text-xs font-medium text-gray-500">Gate</label>
              <select
                v-model="form.gate"
                class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                :disabled="gateResource.loading"
                @change="changeGate(form.gate)"
              >
                <option v-for="gate in GATES" :key="gate" :value="gate">{{ gate }}</option>
              </select>
              <p class="mt-1 text-[11px] text-gray-400">
                Forward moves are checked against the gate rules; moving back is always allowed.
              </p>
            </div>

            <!-- task rollup -->
            <div class="rounded-lg border border-gray-200 p-3">
              <div class="flex items-center justify-between text-xs text-gray-600">
                <span class="font-medium">Tasks</span>
                <span>{{ detail.done_tasks }}/{{ detail.total_tasks }} done</span>
              </div>
              <div class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-gray-200">
                <div
                  class="h-full rounded-full"
                  :class="detail.task_progress >= 100 ? 'bg-green-500' : 'bg-indigo-500'"
                  :style="{ width: Math.min(detail.task_progress || 0, 100) + '%' }"
                ></div>
              </div>
              <p v-if="detail.blocked_tasks" class="mt-2 text-[11px] font-medium text-red-600">
                {{ detail.blocked_tasks }} blocked — advisory only, it does not refuse a gate move.
              </p>
              <p v-if="detail.total_tasks === 0" class="mt-2 text-[11px] text-gray-400">
                No tasks linked yet. Set “Module” on a task to roll it up here.
              </p>
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="text-xs font-medium text-gray-500">Platform</label>
                <select
                  v-model="form.system_platform"
                  class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                  @change="saveField('system_platform', form.system_platform)"
                >
                  <option v-for="platform in PLATFORMS" :key="platform" :value="platform">
                    {{ platform }}
                  </option>
                </select>
              </div>
              <div>
                <label class="text-xs font-medium text-gray-500">SME Responsible</label>
                <div class="mt-1">
                  <EmployeePicker
                    :model-value="form.sme_responsible"
                    @update:model-value="(value) => saveField('sme_responsible', value)"
                  />
                </div>
              </div>
              <div>
                <label class="text-xs font-medium text-gray-500">Configuration Status</label>
                <select
                  v-model="form.configuration_status"
                  class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                  @change="saveField('configuration_status', form.configuration_status)"
                >
                  <option v-for="status in CONFIG_STATUSES" :key="status" :value="status">
                    {{ status }}
                  </option>
                </select>
              </div>
              <div>
                <label class="text-xs font-medium text-gray-500">Data Migration Status</label>
                <select
                  v-model="form.data_migration_status"
                  class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                  @change="saveField('data_migration_status', form.data_migration_status)"
                >
                  <option v-for="status in MIGRATION_STATUSES" :key="status" :value="status">
                    {{ status }}
                  </option>
                </select>
              </div>
              <div>
                <label class="text-xs font-medium text-gray-500">Target Go-Live</label>
                <input
                  v-model="form.target_go_live"
                  type="date"
                  class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                  @change="saveField('target_go_live', form.target_go_live)"
                />
              </div>
              <div class="flex items-end">
                <label class="flex items-center gap-2 pb-2 text-sm text-gray-700">
                  <input
                    v-model="form.functional_signoff"
                    type="checkbox"
                    class="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                    @change="saveField('functional_signoff', form.functional_signoff ? 1 : 0)"
                  />
                  Functional Sign-off
                </label>
              </div>
            </div>

            <div>
              <label class="text-xs font-medium text-gray-500">Notes</label>
              <textarea
                v-model="form.notes"
                rows="3"
                class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
                @change="saveField('notes', form.notes)"
              ></textarea>
            </div>

            <div class="border-t border-gray-100 pt-4">
              <p class="mb-2 text-xs font-medium text-gray-500">Discussion</p>
              <CommentThread doctype="Agile Module" :name="detail.name" />
            </div>

            <div class="border-t border-gray-100 pt-4">
              <button
                class="text-xs font-medium text-red-600 hover:text-red-700"
                @click="removeModule"
              >
                Delete module
              </button>
            </div>
          </div>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { createResource } from 'frappe-ui'
import EmployeePicker from './EmployeePicker.vue'
import CommentThread from './CommentThread.vue'
import {
  GATES,
  GATE_META,
  PLATFORMS,
  CONFIG_STATUSES,
  MIGRATION_STATUSES,
} from '@/utils/statuses'
import { toDateInput } from '@/utils/format'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // The full module row from the board, so the drawer opens already populated.
  module: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue', 'changed', 'progress'])

const detail = ref(null)

const form = reactive({
  gate: '',
  system_platform: '',
  sme_responsible: null,
  configuration_status: '',
  data_migration_status: '',
  functional_signoff: false,
  target_go_live: '',
  notes: '',
})

function hydrate(data) {
  detail.value = data
  if (!data) return
  form.gate = data.gate || GATES[0]
  form.system_platform = data.system_platform || 'ERPNext'
  form.sme_responsible = data.sme_responsible || null
  form.configuration_status = data.configuration_status || 'Not Started'
  form.data_migration_status = data.data_migration_status || 'Not Started'
  form.functional_signoff = !!data.functional_signoff
  form.target_go_live = toDateInput(data.target_go_live)
  form.notes = data.notes || ''
}

watch(
  () => [props.modelValue, props.module],
  ([open, module]) => {
    if (open) hydrate(module)
  },
  { immediate: true }
)

const gateMeta = computed(() => GATE_META[detail.value?.gate] || GATE_META.Configure)

function close() {
  emit('update:modelValue', false)
}

function applyResult(data) {
  if (data.module) hydrate(data.module)
  if (data.percent_complete != null) emit('progress', data.percent_complete)
  emit('changed')
}

const updateResource = createResource({ url: 'agile_projects.modules.update_module' })

function saveField(field, value) {
  updateResource
    .submit({ module: detail.value.name, fields: { [field]: value ?? '' } })
    .then(applyResult)
    .catch((err) => {
      toast({ title: 'Could not save', text: errorMessage(err), type: 'error' })
      // Put the form back to what the server still holds.
      hydrate(detail.value)
    })
}

const gateResource = createResource({ url: 'agile_projects.modules.update_module_gate' })

function changeGate(gate) {
  gateResource
    .submit({ module: detail.value.name, gate })
    .then(applyResult)
    .catch((err) => {
      toast({
        title: 'Gate move rejected',
        text: errorMessage(err),
        type: 'error',
        timeout: 8000,
      })
      // Snap the select back: the server value never changed, so only the
      // form's own copy is out of step.
      form.gate = detail.value.gate
    })
}

const deleteResource = createResource({ url: 'agile_projects.modules.delete_module' })

function removeModule() {
  deleteResource
    .submit({ module: detail.value.name })
    .then((data) => {
      if (data.percent_complete != null) emit('progress', data.percent_complete)
      toast({ title: 'Module deleted', type: 'success', timeout: 2000 })
      emit('changed')
      close()
    })
    .catch((err) => {
      toast({ title: 'Could not delete module', text: errorMessage(err), type: 'error' })
    })
}
</script>
