<template>
  <div class="flex h-full flex-col">
    <router-view />
    <Toasts />
  </div>
</template>

<script setup>
import Toasts from '@/components/Toasts.vue'
</script>
