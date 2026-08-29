<template>
  <div class="h-full overflow-y-auto px-4 py-6 sm:px-6">
    <div class="mx-auto max-w-3xl space-y-4">
      <!-- not configured at all -->
      <div
        v-if="config.data && !config.data.settings.configured"
        class="rounded-lg border border-orange-200 bg-orange-50 p-4 text-sm text-orange-900"
      >
        <p class="font-medium">Google Sheets sync isn't set up yet</p>
        <ol class="mt-2 list-decimal space-y-1 pl-5 text-xs">
          <li>Create a Google Cloud project and enable the <b>Sheets API</b> and <b>Drive API</b>.</li>
          <li>Create a service account, download its JSON key.</li>
          <li>Paste the key into <b>Agile Google Settings</b> in the desk and tick Enable.</li>
          <li>Create the spreadsheet yourself, then share it with the service account as <b>Editor</b>.</li>
        </ol>
        <p class="mt-2 text-xs">
          Nothing here touches Google until that's done — the rest of the app is unaffected.
        </p>
      </div>

      <!-- configuration -->
      <section class="rounded-lg border border-gray-200 bg-white p-4">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="text-sm font-semibold text-gray-900">Linked spreadsheet</h2>
          <a
            v-if="cfg?.url"
            :href="cfg.url"
            target="_blank"
            rel="noopener"
            class="text-xs font-medium text-indigo-600 hover:underline"
          >
            Open in Google Sheets ↗
          </a>
        </div>

        <div class="grid gap-3 sm:grid-cols-2">
          <div class="sm:col-span-2">
            <label class="text-xs font-medium text-gray-500">Spreadsheet ID or URL</label>
            <input
              v-model="form.spreadsheet_id"
              type="text"
              placeholder="docs.google.com/spreadsheets/d/…/edit"
              class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label class="text-xs font-medium text-gray-500">Tab name</label>
            <input
              v-model="form.sheet_tab"
              type="text"
              class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label class="text-xs font-medium text-gray-500">Direction</label>
            <select
              v-model="form.direction"
              class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            >
              <option value="push">Push only — the sheet mirrors ERPNext</option>
              <option value="two_way">Two-way — sheet edits come back</option>
            </select>
          </div>
          <div v-if="form.direction === 'two_way'">
            <label class="text-xs font-medium text-gray-500">If both sides changed</label>
            <select
              v-model="form.conflict_policy"
              class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            >
              <option value="erpnext_wins">ERPNext wins</option>
              <option value="sheet_wins">Sheet wins</option>
              <option value="newest_wins">Most recent wins</option>
            </select>
          </div>
          <div v-if="form.direction === 'two_way'">
            <label class="text-xs font-medium text-gray-500">Safety limit (rows per sync)</label>
            <input
              v-model.number="form.max_changes_per_sync"
              type="number"
              min="1"
              class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            />
          </div>
        </div>

        <label class="mt-3 flex items-center gap-2 text-sm text-gray-700">
          <input
            v-model="form.enabled"
            type="checkbox"
            class="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
          />
          Sync automatically (about every 5 minutes)
        </label>

        <p
          v-if="config.data?.settings?.service_account_email"
          class="mt-3 rounded bg-gray-50 px-3 py-2 text-xs text-gray-600"
        >
          Share the spreadsheet with
          <code class="font-mono">{{ config.data.settings.service_account_email }}</code>
          as an <b>Editor</b>, or the sync can't read it.
        </p>

        <div class="mt-3 flex flex-wrap gap-2">
          <Button variant="solid" :loading="save.loading" @click="saveConfig">Save</Button>
          <Button variant="subtle" :loading="test.loading" @click="testConnection">
            Test connection
          </Button>
          <Button variant="subtle" :loading="syncing" @click="run(true)">Preview changes</Button>
          <Button variant="subtle" :loading="syncing" @click="run(false)">Sync now</Button>
        </div>

        <p v-if="cfg?.last_error" class="mt-3 rounded bg-red-50 px-3 py-2 text-xs text-red-800">
          {{ cfg.last_error }}
        </p>
        <p v-else-if="cfg?.last_synced_at" class="mt-3 text-xs text-gray-500">
          Last synced {{ formatDateTime(cfg.last_synced_at) }}
        </p>
      </section>

      <!-- dry-run / result -->
      <section
        v-if="result"
        class="rounded-lg border p-4"
        :class="result.status === 'halted' ? 'border-red-300 bg-red-50' : 'border-gray-200 bg-white'"
      >
        <h2 class="text-sm font-semibold text-gray-900">
          {{ result.dry_run ? 'Preview — nothing was written' : 'Sync result' }}
        </h2>

        <p v-if="result.halted" class="mt-2 text-sm text-red-800">{{ result.halted }}</p>

        <div v-else class="mt-2 space-y-2 text-sm">
          <p class="text-gray-600">
            {{ result.inbound.applied.length }} row{{ result.inbound.applied.length === 1 ? '' : 's' }}
            {{ result.dry_run ? 'would change' : 'changed' }} ·
            {{ result.inbound.created.length }} new ·
            {{ result.inbound.rejected.length }} rejected ·
            {{ result.pushed }} pushed out
          </p>

          <ul v-if="result.inbound.applied.length" class="space-y-1">
            <li
              v-for="item in result.inbound.applied"
              :key="item.task + item.row"
              class="rounded border border-gray-200 px-2 py-1 text-xs"
            >
              <span class="font-mono text-gray-500">{{ item.task }}</span>
              <span class="text-gray-700">
                — {{ Object.keys(item.fields).join(', ') }}
              </span>
            </li>
          </ul>

          <ul v-if="result.inbound.rejected.length" class="space-y-1">
            <li
              v-for="item in result.inbound.rejected"
              :key="'r' + item.row"
              class="rounded border border-orange-200 bg-orange-50 px-2 py-1 text-xs text-orange-900"
            >
              Row {{ item.row }}<span v-if="item.task"> ({{ item.task }})</span>: {{ item.error }}
            </li>
          </ul>
        </div>
      </section>

      <!-- audit log -->
      <section class="rounded-lg border border-gray-200 bg-white p-4">
        <div class="mb-2 flex items-center justify-between">
          <h2 class="text-sm font-semibold text-gray-900">Recent changes from the sheet</h2>
          <Button variant="ghost" size="sm" :loading="logs.loading" @click="logs.reload()">
            Refresh
          </Button>
        </div>
        <p v-if="!logs.data?.length" class="py-6 text-center text-sm text-gray-400">
          Nothing yet.
        </p>
        <table v-else class="w-full text-xs">
          <thead class="text-left text-gray-500">
            <tr>
              <th class="py-1">When</th>
              <th>Task</th>
              <th>Field</th>
              <th>Was</th>
              <th>Now</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in logs.data" :key="row.name" class="border-t border-gray-100">
              <td class="py-1 text-gray-500">{{ formatDateTime(row.creation) }}</td>
              <td class="font-mono text-gray-600">{{ row.task || '—' }}</td>
              <td class="text-gray-700">{{ row.field || row.outcome }}</td>
              <td class="text-gray-500">{{ row.old_value }}</td>
              <td class="text-gray-900">{{ row.new_value || row.reason }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { Button, createResource } from 'frappe-ui'
import { formatDateTime } from '@/utils/format'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  project: { type: String, required: true },
  filters: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['open-task', 'changed'])

const cfg = ref(null)
const result = ref(null)
const syncing = ref(false)

const form = reactive({
  spreadsheet_id: '',
  sheet_tab: 'Tasks',
  direction: 'push',
  conflict_policy: 'erpnext_wins',
  max_changes_per_sync: 25,
  enabled: false,
})

const config = createResource({
  url: 'agile_projects.google.api.get_sync_config',
  makeParams: () => ({ project: props.project }),
  auto: true,
  onSuccess(data) {
    cfg.value = data.config
    if (data.config) {
      Object.assign(form, {
        spreadsheet_id: data.config.spreadsheet_id || '',
        sheet_tab: data.config.sheet_tab || 'Tasks',
        direction: data.config.direction || 'push',
        conflict_policy: data.config.conflict_policy || 'erpnext_wins',
        max_changes_per_sync: data.config.max_changes_per_sync || 25,
        enabled: !!data.config.enabled,
      })
    }
  },
  onError(err) {
    toast({ title: 'Could not load sync settings', text: errorMessage(err), type: 'error' })
  },
})

const logs = createResource({
  url: 'agile_projects.google.api.get_sync_log',
  makeParams: () => ({ project: props.project }),
  auto: true,
})

watch(
  () => props.project,
  () => {
    config.reload()
    logs.reload()
    result.value = null
  }
)

const save = createResource({ url: 'agile_projects.google.api.save_sync_config' })
const test = createResource({ url: 'agile_projects.google.api.test_connection' })
const sync = createResource({ url: 'agile_projects.google.api.sync_now' })

function saveConfig() {
  save
    .submit({ project: props.project, ...form, enabled: form.enabled ? 1 : 0 })
    .then(() => {
      toast({ title: 'Saved', type: 'success', timeout: 2000 })
      config.reload()
    })
    .catch((err) => toast({ title: 'Could not save', text: errorMessage(err), type: 'error' }))
}

function testConnection() {
  test
    .submit({ project: props.project })
    .then((data) => {
      if (!data.tab_found) {
        toast({
          title: `Connected to "${data.name}", but no tab called "${form.sheet_tab}"`,
          text: `Tabs found: ${data.tabs.join(', ')}`,
          type: 'warning',
          timeout: 9000,
        })
      } else {
        toast({ title: `Connected to "${data.name}"`, type: 'success' })
      }
    })
    .catch((err) =>
      toast({ title: 'Connection failed', text: errorMessage(err), type: 'error', timeout: 10000 })
    )
}

function run(dryRun) {
  syncing.value = true
  sync
    .submit({ project: props.project, dry_run: dryRun ? 1 : 0 })
    .then((data) => {
      result.value = data
      if (!dryRun) {
        logs.reload()
        config.reload()
        emit('changed')
      }
    })
    .catch((err) =>
      toast({ title: 'Sync failed', text: errorMessage(err), type: 'error', timeout: 10000 })
    )
    .finally(() => {
      syncing.value = false
    })
}

defineExpose({ reload: () => { config.reload(); logs.reload() } })
</script>
