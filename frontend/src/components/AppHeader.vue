<template>
  <header class="sticky top-0 z-10 border-b border-gray-200 bg-white">
    <div class="flex h-14 items-center justify-between gap-4 px-4 sm:px-6">
      <div class="flex min-w-0 items-center gap-3">
        <router-link to="/" class="flex shrink-0 items-center gap-2">
          <img src="/favicon.svg" alt="" class="h-7 w-7 rounded" />
          <span class="hidden text-sm font-semibold text-gray-900 sm:block">Agile Projects</span>
        </router-link>
        <div v-if="$slots.default" class="min-w-0 border-l border-gray-200 pl-3">
          <slot />
        </div>
      </div>
      <div class="flex shrink-0 items-center gap-3">
        <div class="flex items-center gap-2">
          <img
            v-if="userInfo.data?.user_image"
            :src="userInfo.data.user_image"
            alt=""
            class="h-7 w-7 rounded-full object-cover"
          />
          <span
            v-else
            class="flex h-7 w-7 items-center justify-center rounded-full bg-indigo-100 text-xs font-semibold text-indigo-700"
          >
            {{ initials(userInfo.data?.full_name || session.user) }}
          </span>
          <span class="hidden max-w-[160px] truncate text-sm text-gray-700 md:block">
            {{ userInfo.data?.full_name || session.user }}
          </span>
        </div>
        <Button variant="ghost" size="sm" :loading="logout.loading" @click="logout.submit()">
          Log out
        </Button>
      </div>
    </div>
  </header>
</template>

<script setup>
import { onMounted } from 'vue'
import { Button } from 'frappe-ui'
import { session, logout, userInfo } from '@/data/session'
import { initials } from '@/utils/format'

onMounted(() => {
  if (!userInfo.data && !userInfo.loading) {
    userInfo.fetch()
  }
})
</script>
