<template>
  <div class="flex items-center gap-1">
    <!-- Dropdown wraps the slot in its own trigger; no click handler needed -->
    <Dropdown :options="options">
      <Button variant="ghost" size="sm">
        Views<span v-if="views.data?.length"> ({{ views.data.length }})</span> ▾
      </Button>
    </Dropdown>

    <Dialog
      v-model="showSave"
      :options="{ title: 'Save current view', size: 'sm' }"
    >
      <template #body-content>
        <form class="space-y-3" @submit.prevent="save">
          <div>
            <label class="text-xs font-medium text-gray-500">Name</label>
            <input
              ref="nameInput"
              v-model="viewName"
              type="text"
              placeholder="e.g. My blocked tasks"
              class="mt-1 w-full rounded-md border-gray-300 text-sm focus:border-indigo-500 focus:ring-indigo-500"
              required
            />
          </div>
          <label class="flex items-center gap-2 text-sm text-gray-700">
            <input
              v-model="isDefault"
              type="checkbox"
              class="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
            />
            Make this my default {{ viewType }} view
          </label>
          <p class="text-xs text-gray-500">
            Saves the current filters for the <strong>{{ viewType }}</strong> view of this project.
          </p>
          <div class="flex justify-end gap-2 pt-1">
            <Button variant="subtle" type="button" @click="showSave = false">Cancel</Button>
            <Button variant="solid" type="submit" :loading="saveResource.loading">Save</Button>
          </div>
        </form>
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import { Button, Dialog, Dropdown, createResource } from 'frappe-ui'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  project: { type: String, required: true },
  viewType: { type: String, default: 'board' },
  filters: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['apply'])

const showSave = ref(false)
const viewName = ref('')
const isDefault = ref(false)
const nameInput = ref(null)

const views = createResource({
  url: 'agile_projects.views.get_views',
  makeParams: () => ({ project: props.project }),
  auto: true,
})

const saveResource = createResource({ url: 'agile_projects.views.save_view' })
const deleteResource = createResource({ url: 'agile_projects.views.delete_view' })

const options = computed(() => {
  const saved = (views.data || []).map((view) => ({
    label: `${view.view_name}${view.is_default ? ' ★' : ''}`,
    onClick: () => emit('apply', view),
  }))
  const actions = [
    {
      label: '＋ Save current view…',
      onClick: () => {
        viewName.value = ''
        isDefault.value = false
        showSave.value = true
        nextTick(() => nameInput.value?.focus())
      },
    },
  ]
  if (saved.length) {
    actions.push({
      label: '🗑 Delete a view…',
      onClick: removePrompt,
    })
  }
  return saved.length ? [...saved, ...actions] : actions
})

function save() {
  if (!viewName.value.trim()) return
  saveResource
    .submit({
      view_name: viewName.value.trim(),
      view_type: props.viewType,
      project: props.project,
      filters: props.filters,
      is_default: isDefault.value ? 1 : 0,
    })
    .then(() => {
      toast({ title: 'View saved', type: 'success', timeout: 2000 })
      showSave.value = false
      views.reload()
    })
    .catch((err) => {
      toast({ title: 'Could not save view', text: errorMessage(err), type: 'error' })
    })
}

function removePrompt() {
  const list = views.data || []
  const name = window.prompt(
    `Type the name of the view to delete:\n\n${list.map((v) => v.view_name).join('\n')}`
  )
  if (!name) return
  const match = list.find((v) => v.view_name.toLowerCase() === name.trim().toLowerCase())
  if (!match) {
    toast({ title: 'No view with that name', type: 'warning' })
    return
  }
  deleteResource
    .submit({ name: match.name })
    .then(() => {
      toast({ title: 'View deleted', type: 'success', timeout: 2000 })
      views.reload()
    })
    .catch((err) => {
      toast({ title: 'Could not delete view', text: errorMessage(err), type: 'error' })
    })
}
</script>
