<template>
  <div class="thin-scrollbar h-full overflow-y-auto">
    <div class="mx-auto max-w-4xl px-4 py-5 sm:px-6">
      <!-- summary -->
      <div class="mb-4 flex flex-wrap items-center gap-3">
        <div>
          <h2 class="text-sm font-semibold text-gray-900">Cutover runbook</h2>
          <p class="text-xs text-gray-500">
            The ordered go-live sequence. A step records who owns it, when it was meant to run and
            when it actually ran.
          </p>
        </div>
        <span class="flex-1"></span>
        <div v-if="steps.length" class="text-right">
          <p class="text-sm font-semibold text-gray-900">{{ doneCount }}/{{ steps.length }}</p>
          <p class="text-[11px] text-gray-500">steps complete</p>
        </div>
        <Button variant="solid" size="sm" @click="showNew = true">Add step</Button>
      </div>

      <div v-if="runbook.loading && !steps.length" class="py-16 text-center text-sm text-gray-500">
        Loading runbook…
      </div>

      <div
        v-else-if="!steps.length"
        class="rounded-xl border border-dashed border-gray-300 px-6 py-14 text-center"
      >
        <p class="text-sm font-medium text-gray-700">No cutover steps yet</p>
        <p class="mx-auto mt-1 max-w-md text-sm text-gray-500">
          Cutover is the riskiest hour of a rollout and the one nobody wants to improvise. Write the
          sequence down while it is still calm.
        </p>
      </div>

      <ol v-else class="space-y-2">
        <li
          v-for="(step, index) in steps"
          :key="step.name"
          class="rounded-lg border bg-white p-3 shadow-sm"
          :class="step.status === 'Failed' ? 'border-red-300' : 'border-gray-200'"
        >
          <div class="flex items-start gap-3">
            <span
              class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gray-100 text-[11px] font-semibold text-gray-600"
            >
              {{ index + 1 }}
            </span>

            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <p class="text-sm font-medium text-gray-900">{{ step.title }}</p>
                <span
                  class="rounded px-1.5 py-0.5 text-[10px] font-medium"
                  :class="CUTOVER_STATUS_COLORS[step.status]"
                >
                  {{ step.status }}
                </span>
                <span
                  v-if="step.module_label"
                  class="rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] text-indigo-700"
                >
                  {{ step.module_label }}
                </span>
                <span
                  v-if="step.signed_off_by"
                  class="rounded bg-green-50 px-1.5 py-0.5 text-[10px] text-green-700"
                  :title="'Signed off ' + formatDateTime(step.signed_off_at)"
                >
                  ✓ {{ step.signed_off_by }}
                </span>
              </div>

              <p v-if="step.description" class="mt-1 whitespace-pre-line text-xs text-gray-600">
                {{ step.description }}
              </p>

              <!-- blocked-by indicator -->
              <p
                v-if="blockerOf(step)"
                class="mt-1.5 rounded bg-amber-50 px-2 py-1 text-[11px] text-amber-800"
              >
                Waiting on step “{{ step.depends_on_title }}” ({{ step.depends_on_status }})
              </p>

              <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-gray-500">
                <span v-if="step.planned_start || step.planned_end">
                  Planned {{ formatDateTime(step.planned_start) || '—' }} →
                  {{ formatDateTime(step.planned_end) || '—' }}
                </span>
                <span v-if="step.actual_start" class="font-medium text-gray-700">
                  Actual {{ formatDateTime(step.actual_start) }}
                  <template v-if="step.actual_end"> → {{ formatDateTime(step.actual_end) }}</template>
                </span>
                <span v-if="elapsed(step)" class="font-medium text-indigo-600">
                  ⏱ {{ elapsed(step) }}
                </span>
                <span v-if="step.owner_name || step.owner_employee">
                  👤 {{ step.owner_name || step.owner_employee }}
                </span>
              </div>
            </div>

            <div class="flex shrink-0 flex-col items-end gap-1">
              <Button
                v-if="step.status === 'Pending'"
                variant="subtle"
                size="sm"
                @click="run('start_step', { step: step.name }, 'Step started')"
              >
                Start
              </Button>
              <Button
                v-if="step.status === 'In Progress'"
                variant="solid"
                size="sm"
                @click="run('complete_step', { step: step.name, status: 'Done' }, 'Step complete')"
              >
                Complete
              </Button>
              <Button
                v-if="step.status === 'Done' && !step.signed_off_by"
                variant="subtle"
                size="sm"
                @click="run('signoff_step', { step: step.name }, 'Step signed off')"
              >
                Sign off
              </Button>
              <button
                v-if="step.status !== 'Done'"
                class="text-[11px] text-gray-400 hover:text-gray-600"
                @click="run('complete_step', { step: step.name, status: 'Skipped' }, 'Step skipped')"
              >
                Skip
              </button>
              <button
                v-if="step.status === 'In Progress'"
                class="text-[11px] text-red-500 hover:text-red-700"
                @click="run('complete_step', { step: step.name, status: 'Failed' }, 'Step marked failed')"
              >
                Mark failed
              </button>
            </div>
          </div>
        </li>
      </ol>
    </div>

    <NewCutoverStepDialog
      v-model="showNew"
      :project="project"
      :steps="steps"
      @created="onCreated"
    />
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import { Button, createResource } from 'frappe-ui'
import NewCutoverStepDialog from '@/components/NewCutoverStepDialog.vue'
import { CUTOVER_STATUS_COLORS } from '@/utils/statuses'
import { formatDateTime } from '@/utils/format'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  project: { type: String, required: true },
})

const emit = defineEmits(['changed'])

const showNew = ref(false)

const runbook = createResource({
  url: 'agile_projects.modules.get_cutover',
  makeParams: () => ({ project: props.project }),
  auto: true,
  onError(err) {
    toast({ title: 'Failed to load runbook', text: errorMessage(err), type: 'error' })
  },
})

watch(
  () => props.project,
  () => runbook.reload()
)

const steps = computed(() => runbook.data?.steps || [])

const doneCount = computed(() => steps.value.filter((s) => s.status === 'Done').length)

// A dependency is satisfied by Done or Skipped, matching the controller.
function blockerOf(step) {
  if (!step.depends_on || !step.depends_on_status) return false
  return !['Done', 'Skipped'].includes(step.depends_on_status)
}

// Re-read on a timer so a running step's clock advances instead of freezing
// at whatever the last render happened to be.
const now = ref(Date.now())
const ticker = setInterval(() => (now.value = Date.now()), 30000)
onUnmounted(() => clearInterval(ticker))

function elapsed(step) {
  if (!step.actual_start) return null
  const start = new Date(String(step.actual_start).replace(' ', 'T'))
  const end = step.actual_end
    ? new Date(String(step.actual_end).replace(' ', 'T'))
    : new Date(now.value)
  const minutes = Math.round((end - start) / 60000)
  if (isNaN(minutes) || minutes < 0) return null
  if (minutes < 60) return `${minutes}m`
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

// One resource per endpoint: `url` is read when the resource is created, so
// reassigning it would keep posting to whichever endpoint was registered first.
const actions = {
  start_step: createResource({ url: 'agile_projects.modules.start_step' }),
  complete_step: createResource({ url: 'agile_projects.modules.complete_step' }),
  signoff_step: createResource({ url: 'agile_projects.modules.signoff_step' }),
}

function run(endpoint, params, successTitle) {
  actions[endpoint]
    .submit(params)
    .then(() => {
      toast({ title: successTitle, type: 'success', timeout: 2000 })
      runbook.reload()
      emit('changed')
    })
    .catch((err) => {
      toast({ title: 'Action rejected', text: errorMessage(err), type: 'error', timeout: 8000 })
      runbook.reload()
    })
}

function onCreated() {
  showNew.value = false
  runbook.reload()
}

defineExpose({ reload: () => runbook.reload() })
</script>
