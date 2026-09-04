<template>
  <!-- Popover, not Dropdown: frappe-ui's Dropdown renders menu items from
       :options and has no slot for a rich panel like this one. -->
  <Popover placement="bottom-end">
    <template #target="{ togglePopover }">
      <button
        class="relative rounded-md p-1.5 text-gray-500 hover:bg-gray-100 hover:text-gray-800"
        title="Notifications"
        @click="onOpen(togglePopover)"
      >
        <span class="text-base leading-none">🔔</span>
        <span
          v-if="unread"
          class="absolute -right-0.5 -top-0.5 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white"
        >
          {{ unread > 99 ? '99+' : unread }}
        </span>
      </button>
    </template>

    <template #body>
      <div class="w-80 rounded-lg bg-white py-1">
        <div class="flex items-center gap-2 border-b border-gray-100 px-3 py-2">
          <p class="text-sm font-semibold text-gray-900">Notifications</p>
          <span class="flex-1"></span>
          <button
            v-if="unread"
            class="text-[11px] font-medium text-indigo-600 hover:text-indigo-700"
            @click="markAllRead"
          >
            Mark all read
          </button>
        </div>

        <p v-if="!items.length" class="px-3 py-8 text-center text-sm text-gray-500">
          Nothing yet. Mentions and assignments land here.
        </p>

        <ul v-else class="thin-scrollbar max-h-96 overflow-y-auto">
          <li v-for="item in items" :key="item.name">
            <button
              class="flex w-full gap-2 px-3 py-2 text-left hover:bg-gray-50"
              :class="{ 'bg-indigo-50/40': !item.read }"
              @click="open(item)"
            >
              <span
                class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full"
                :class="item.read ? 'bg-transparent' : 'bg-indigo-500'"
              ></span>
              <span class="min-w-0 flex-1">
                <span class="block text-sm leading-snug text-gray-800">{{ item.subject }}</span>
                <span class="mt-0.5 block text-[11px] text-gray-400">
                  {{ formatDateTime(item.creation) }}
                </span>
              </span>
            </button>
          </li>
        </ul>
      </div>
    </template>
  </Popover>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Popover, createResource } from 'frappe-ui'
import { useLiveRefresh, useRealtime } from '@/data/socket'
import { formatDateTime } from '@/utils/format'
import { toast, errorMessage } from '@/utils/toast'

const router = useRouter()

const feed = createResource({
  url: 'agile_projects.collaboration.get_notifications',
  auto: true,
  // Silent: a failing bell should never interrupt what someone is doing.
  onError() {},
})

const items = computed(() => feed.data?.notifications || [])
const unread = computed(() => feed.data?.unread || 0)

function refetch() {
  feed.reload()
}

// Frappe publishes `notification` to the recipient's own room on insert.
useRealtime('notification', refetch)
// ...and this keeps the count moving when the socket never connects.
useLiveRefresh(refetch)

const readOne = createResource({ url: 'agile_projects.collaboration.mark_notification_read' })
const readAll = createResource({ url: 'agile_projects.collaboration.mark_all_notifications_read' })

function open(item) {
  if (!item.read) {
    readOne.submit({ notification: item.name }).then(refetch).catch(() => {})
  }
  if (!item.link) {
    toast({ title: 'That item is no longer available', type: 'info' })
    return
  }
  // Links are built server-side as absolute /agile paths; the router's history
  // base is already /agile, so strip it before pushing.
  router.push(item.link.replace(/^\/agile/, '') || '/')
}

function markAllRead() {
  readAll
    .submit()
    .then(refetch)
    .catch((err) => {
      toast({ title: 'Could not mark as read', text: errorMessage(err), type: 'error' })
    })
}

function onOpen(togglePopover) {
  refetch()
  togglePopover()
}
</script>
