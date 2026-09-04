<template>
  <div class="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-80 flex-col gap-2">
    <transition-group name="fade">
      <div
        v-for="item in toasts"
        :key="item.id"
        class="pointer-events-auto flex items-start gap-3 rounded-lg border p-3 shadow-lg"
        :class="styles[item.type] || styles.info"
      >
        <span class="mt-0.5 text-base leading-none">{{ icons[item.type] || icons.info }}</span>
        <div class="min-w-0 flex-1">
          <p class="text-sm font-medium">{{ item.title }}</p>
          <p v-if="item.text" class="mt-0.5 whitespace-pre-line text-xs opacity-80">
            {{ item.text }}
          </p>
        </div>
        <button
          class="text-xs opacity-60 hover:opacity-100"
          aria-label="Dismiss"
          @click="dismissToast(item.id)"
        >
          ✕
        </button>
      </div>
    </transition-group>
  </div>
</template>

<script setup>
import { toasts, dismissToast } from '@/utils/toast'

const styles = {
  info: 'border-blue-200 bg-blue-50 text-blue-900',
  success: 'border-green-200 bg-green-50 text-green-900',
  error: 'border-red-200 bg-red-50 text-red-900',
  warning: 'border-orange-200 bg-orange-50 text-orange-900',
}

const icons = {
  info: 'ℹ️',
  success: '✅',
  error: '⛔',
  warning: '⚠️',
}
</script>
