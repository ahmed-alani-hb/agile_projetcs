<template>
  <div>
    <div class="flex items-center gap-2">
      <p class="text-xs font-medium text-gray-500">
        Files<span v-if="files.length"> ({{ files.length }})</span>
      </p>
      <span class="flex-1"></span>
      <label
        class="cursor-pointer rounded-md px-2 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-50"
        :class="{ 'pointer-events-none opacity-50': uploading }"
      >
        {{ uploading ? 'Uploading…' : '+ Attach' }}
        <input type="file" class="hidden" :disabled="uploading" @change="upload" />
      </label>
    </div>

    <p v-if="!files.length && !uploading" class="mt-1 text-[11px] text-gray-400">
      Attach the evidence a sign-off will be asked for later.
    </p>

    <ul v-else class="mt-2 space-y-1.5">
      <li
        v-for="file in files"
        :key="file.name"
        class="flex items-center gap-2 rounded-md border border-gray-200 px-2.5 py-1.5"
      >
        <a
          :href="file.file_url"
          target="_blank"
          rel="noopener"
          class="min-w-0 flex-1 truncate text-sm text-indigo-700 hover:underline"
          :title="file.file_name"
        >
          {{ file.file_name }}
        </a>
        <span class="shrink-0 text-[11px] text-gray-400">{{ formatSize(file.file_size) }}</span>
        <span class="shrink-0 text-[11px] text-gray-400" :title="file.user_name">
          {{ initials(file.user_name) }}
        </span>
        <button
          v-if="file.owner === session.user"
          class="shrink-0 text-xs text-gray-400 hover:text-red-600"
          title="Remove file"
          @click="remove(file)"
        >
          ✕
        </button>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { createResource } from 'frappe-ui'
import { session } from '@/data/session'
import { initials } from '@/utils/format'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  doctype: { type: String, required: true },
  name: { type: String, default: null },
})

const uploading = ref(false)

const list = createResource({
  url: 'agile_projects.collaboration.get_attachments',
  onError(err) {
    toast({ title: 'Failed to load files', text: errorMessage(err), type: 'error' })
  },
})

const files = computed(() => list.data?.files || [])

watch(
  () => [props.doctype, props.name],
  ([doctype, name]) => {
    if (doctype && name) list.submit({ doctype, name })
  },
  { immediate: true }
)

function formatSize(bytes) {
  const size = Number(bytes) || 0
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

// Uploads go through Frappe's own endpoint rather than a custom one: it
// already handles permissions, size limits and storage. is_private is
// non-negotiable — a public File is readable by URL to anyone who has it.
async function upload(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file || !props.name) return

  const form = new FormData()
  form.append('file', file, file.name)
  form.append('is_private', '1')
  form.append('doctype', props.doctype)
  form.append('docname', props.name)

  uploading.value = true
  try {
    const response = await fetch('/api/method/upload_file', {
      method: 'POST',
      headers: { 'X-Frappe-CSRF-Token': window.csrf_token },
      credentials: 'same-origin',
      body: form,
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(payload?._server_messages || payload?.exception || 'Upload failed')
    }
    toast({ title: 'File attached', type: 'success', timeout: 2000 })
    list.submit({ doctype: props.doctype, name: props.name })
  } catch (err) {
    toast({ title: 'Could not attach file', text: errorMessage(err), type: 'error', timeout: 8000 })
  } finally {
    uploading.value = false
  }
}

const removeResource = createResource({ url: 'agile_projects.collaboration.delete_attachment' })

function remove(file) {
  removeResource
    .submit({ file: file.name })
    .then(() => list.submit({ doctype: props.doctype, name: props.name }))
    .catch((err) => {
      toast({ title: 'Could not remove file', text: errorMessage(err), type: 'error' })
    })
}
</script>
