<template>
  <div>
    <p v-if="feed.loading && !entries.length" class="py-8 text-center text-sm text-gray-500">
      Loading activity…
    </p>

    <p
      v-else-if="!entries.length"
      class="rounded-lg border border-dashed border-gray-300 py-8 text-center text-sm text-gray-500"
    >
      Nothing has happened here yet. Changes and comments will appear as they do.
    </p>

    <ol v-else class="relative space-y-4 border-l border-gray-200 pl-5">
      <li v-for="entry in entries" :key="entry.kind + entry.name" class="relative">
        <span
          class="absolute -left-[1.4rem] top-1.5 h-2 w-2 rounded-full ring-2 ring-white"
          :class="entry.kind === 'comment' ? 'bg-indigo-500' : 'bg-gray-300'"
        ></span>

        <div class="flex items-baseline gap-2">
          <span class="text-sm font-medium text-gray-900">{{ entry.user_name }}</span>
          <span class="text-[11px] text-gray-400">{{ formatDateTime(entry.creation) }}</span>
        </div>

        <ul v-if="entry.kind === 'change'" class="mt-0.5 space-y-0.5">
          <li v-for="(line, index) in entry.lines" :key="index" class="text-sm text-gray-600">
            {{ line }}
          </li>
        </ul>

        <!-- Sanitised server-side on write (collaboration.add_comment). -->
        <div
          v-else
          class="prose-sm mt-0.5 max-w-none break-words rounded-md bg-gray-50 px-2.5 py-1.5 text-sm text-gray-700"
          v-html="entry.content"
        ></div>
      </li>
    </ol>
  </div>
</template>

<script setup>
import { computed, watch } from 'vue'
import { createResource } from 'frappe-ui'
import { formatDateTime } from '@/utils/format'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  doctype: { type: String, required: true },
  name: { type: String, default: null },
})

const feed = createResource({
  url: 'agile_projects.collaboration.get_activity',
  onError(err) {
    toast({ title: 'Failed to load activity', text: errorMessage(err), type: 'error' })
  },
})

const entries = computed(() => feed.data?.entries || [])

watch(
  () => [props.doctype, props.name],
  ([doctype, name]) => {
    if (doctype && name) feed.submit({ doctype, name })
  },
  { immediate: true }
)

defineExpose({
  reload: () => props.name && feed.submit({ doctype: props.doctype, name: props.name }),
})
</script>
