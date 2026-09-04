<template>
  <div class="flex h-full flex-col">
    <div class="min-h-0 flex-1">
      <p v-if="thread.loading && !comments.length" class="py-8 text-center text-sm text-gray-500">
        Loading discussion…
      </p>

      <p
        v-else-if="!comments.length"
        class="rounded-lg border border-dashed border-gray-300 py-8 text-center text-sm text-gray-500"
      >
        No discussion yet. Ask a question, or record why this is where it is.
      </p>

      <ul v-else class="space-y-3">
        <li v-for="comment in comments" :key="comment.name" class="flex gap-2.5">
          <img
            v-if="comment.user_image"
            :src="comment.user_image"
            :alt="comment.user_name"
            class="mt-0.5 h-7 w-7 shrink-0 rounded-full object-cover"
          />
          <span
            v-else
            class="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-[10px] font-semibold text-indigo-700"
          >
            {{ initials(comment.user_name) }}
          </span>

          <div class="min-w-0 flex-1">
            <div class="flex items-baseline gap-2">
              <span class="text-sm font-medium text-gray-900">{{ comment.user_name }}</span>
              <span class="text-[11px] text-gray-400">{{ formatDateTime(comment.creation) }}</span>
              <span class="flex-1"></span>
              <button
                v-if="canDelete(comment)"
                class="text-[11px] text-gray-400 hover:text-red-600"
                title="Delete comment"
                @click="remove(comment)"
              >
                ✕
              </button>
            </div>
            <!-- Sanitised server-side on write (collaboration.add_comment). -->
            <div
              class="prose-sm mt-0.5 max-w-none break-words text-sm text-gray-700"
              v-html="comment.content"
            ></div>
          </div>
        </li>
      </ul>
    </div>

    <!-- composer -->
    <div class="mt-4 border-t border-gray-200 pt-3">
      <div
        class="rounded-md border border-gray-300 px-3 py-2 focus-within:border-indigo-500 focus-within:ring-1 focus-within:ring-indigo-500"
      >
        <TextEditor
          ref="editor"
          :content="draft"
          :editable="true"
          :mentions="mentionConfig"
          placeholder="Write a comment… type @ to mention someone"
          editor-class="prose-sm max-w-none min-h-[56px] focus:outline-none text-sm"
          @change="(html) => (draft = html)"
        />
      </div>
      <div class="mt-2 flex items-center gap-2">
        <p class="text-[11px] text-gray-400">
          @mentions notify people who can already see this.
        </p>
        <span class="flex-1"></span>
        <Button
          variant="solid"
          size="sm"
          :loading="post.loading"
          :disabled="!hasDraft"
          @click="submit"
        >
          Comment
        </Button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Button, TextEditor, createResource } from 'frappe-ui'
import { session } from '@/data/session'
import { useDocRoom, useLiveRefresh, useRealtime } from '@/data/socket'
import { formatDateTime, initials } from '@/utils/format'
import { toast, errorMessage } from '@/utils/toast'

const props = defineProps({
  doctype: { type: String, required: true },
  name: { type: String, default: null },
})

const emit = defineEmits(['posted'])

const draft = ref('')
const editor = ref(null)

// The drawer stays mounted across documents, so load from a prop watcher
// rather than `auto: true` — same reason as TimesheetSection.
const thread = createResource({
  url: 'agile_projects.collaboration.get_comments',
  onError(err) {
    toast({ title: 'Failed to load discussion', text: errorMessage(err), type: 'error' })
  },
})

const comments = computed(() => thread.data?.comments || [])

watch(
  () => [props.doctype, props.name],
  ([doctype, name]) => {
    draft.value = ''
    if (doctype && name) thread.submit({ doctype, name })
  },
  { immediate: true }
)

// Live append: join the document's room and follow it as the drawer moves.
const joinRoom = useDocRoom(() =>
  props.name ? { doctype: props.doctype, name: props.name } : null
)
watch(() => [props.doctype, props.name], () => joinRoom(), { immediate: true })

// Without a socket the thread would never see anyone else's comment; poll
// as a fallback and whenever the tab comes back into focus.
useLiveRefresh(() => {
  if (props.name) thread.submit({ doctype: props.doctype, name: props.name })
})

useRealtime('agile_comment', (payload) => {
  if (payload?.doctype !== props.doctype || payload?.name !== props.name) return
  if (!thread.data) return
  // Our own comment is already in the list from the POST response.
  if (comments.value.some((c) => c.name === payload.comment?.name)) return
  thread.data.comments = [...comments.value, payload.comment]
})

// A mention targets a User. Sourcing this from Employee (as the first version
// did) drops anyone whose optional Employee.user_id is blank, plus anyone with
// app access and no Employee record at all.
const mentionable = createResource({
  url: 'agile_projects.collaboration.get_mentionable_users',
  cache: 'agile:mention_users',
  auto: true,
})

// `value` becomes the mention's data-id, which the server reads back out of the
// saved HTML to decide who to notify.
const mentionOptions = computed(() =>
  (mentionable.data || []).map((user) => ({
    label: user.full_name || user.name,
    value: user.name,
  }))
)

// Deliberately the object-with-getter form, and it must stay that way.
// frappe-ui's TextEditor builds its extensions exactly once in onMounted and
// never watches this prop, so handing it a plain array snapshots whatever the
// array was at mount — for an async list, permanently empty, with no error
// because `[] && ...` is truthy. The mention extension's own option type is
// MaybeRefOrGetter and it calls toValue() on every keystroke, but the array
// branch of TextEditor's `Array.isArray(props.mentions)` check is what freezes
// it; only the object branch forwards `.mentions` raw to toValue. Hence a
// getter inside an object. Simplifying this back to `:mentions="mentionOptions"`
// reintroduces the bug silently.
const mentionConfig = { mentions: () => mentionOptions.value }

const hasDraft = computed(() => {
  const text = String(draft.value || '')
    .replace(/<[^>]*>/g, '')
    .trim()
  return text.length > 0
})

function canDelete(comment) {
  return comment.owner === session.user
}

const post = createResource({ url: 'agile_projects.collaboration.add_comment' })

function submit() {
  if (!hasDraft.value || !props.name) return
  post
    .submit({ doctype: props.doctype, name: props.name, content: draft.value })
    .then((data) => {
      if (thread.data && data.comment) {
        thread.data.comments = [...comments.value, data.comment]
      }
      draft.value = ''
      editor.value?.editor?.commands?.clearContent?.(true)
      emit('posted')
    })
    .catch((err) => {
      toast({ title: 'Could not post comment', text: errorMessage(err), type: 'error', timeout: 8000 })
    })
}

const removeResource = createResource({ url: 'agile_projects.collaboration.delete_comment' })

function remove(comment) {
  const previous = comments.value
  thread.data.comments = previous.filter((c) => c.name !== comment.name)
  removeResource.submit({ comment: comment.name }).catch((err) => {
    thread.data.comments = previous
    toast({ title: 'Could not delete comment', text: errorMessage(err), type: 'error' })
  })
}

defineExpose({ reload: () => props.name && thread.submit({ doctype: props.doctype, name: props.name }) })
</script>
