<template>
  <div class="flex h-full flex-col">
    <router-view />
    <Toasts />
  </div>
</template>

<script setup>
import Toasts from '@/components/Toasts.vue'
import { useRealtime } from '@/data/socket'
import { toast } from '@/utils/toast'

// The Sheets sync has published this since it shipped, with nobody listening.
// A halted sync is exactly the thing you want to hear about without hunting
// for the Sheet view.
useRealtime('agile_sheet_sync_halted', (payload) => {
  toast({
    title: 'Google Sheet sync halted',
    text: payload?.message || 'The sync stopped and needs attention.',
    type: 'error',
    timeout: 10000,
  })
})
</script>
