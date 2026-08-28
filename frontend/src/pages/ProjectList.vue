<template>
  <div class="flex h-full flex-col">
    <AppHeader />
    <main class="mx-auto w-full max-w-7xl flex-1 overflow-y-auto px-4 py-8 sm:px-6">
      <div class="mb-6 flex items-center justify-between">
        <div>
          <h1 class="text-xl font-semibold text-gray-900">Projects</h1>
          <p class="mt-1 text-sm text-gray-500">
            {{ projects.data?.length || 0 }} project{{ (projects.data?.length || 0) === 1 ? '' : 's' }}
            · ERPNext portfolio
          </p>
        </div>
        <Button variant="subtle" :loading="projects.loading" @click="projects.reload()">
          Refresh
        </Button>
      </div>

      <div v-if="projects.loading && !projects.data" class="py-16 text-center text-sm text-gray-500">
        Loading projects…
      </div>

      <div
        v-else-if="!projects.data?.length"
        class="rounded-xl border border-dashed border-gray-300 py-16 text-center"
      >
        <p class="text-3xl">🗂️</p>
        <p class="mt-2 text-sm font-medium text-gray-700">No projects yet</p>
        <p class="mt-1 text-sm text-gray-500">
          Create a Project in ERPNext and it will show up here.
        </p>
      </div>

      <div v-else class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <router-link
          v-for="project in projects.data"
          :key="project.name"
          :to="{ name: 'ProjectBoard', params: { projectId: project.name } }"
          class="group rounded-xl border border-gray-200 bg-white p-4 shadow-sm transition hover:border-indigo-300 hover:shadow-md"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <p class="truncate text-sm font-semibold text-gray-900 group-hover:text-indigo-700">
                {{ project.project_name || project.name }}
              </p>
              <p class="mt-0.5 truncate font-mono text-[11px] text-gray-400">{{ project.name }}</p>
            </div>
            <ProgressRing :value="project.percent_complete || 0" />
          </div>

          <div class="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
            <span
              class="rounded-full px-2 py-0.5 font-medium"
              :class="projectStatusPill(project.status)"
            >
              {{ project.status }}
            </span>
            <span v-if="project.priority" class="text-gray-500">{{ project.priority }} priority</span>
            <span v-if="project.expected_end_date" class="text-gray-500">
              Due {{ formatDate(project.expected_end_date) }}
            </span>
          </div>

          <div class="mt-4 grid grid-cols-2 gap-2 border-t border-gray-100 pt-3 text-xs text-gray-600">
            <div>
              <span class="font-semibold text-gray-900">{{ project.done_tasks }}</span>
              / {{ project.total_tasks }} tasks done
            </div>
            <div>
              <span class="font-semibold text-gray-900">{{ project.checklist_signed_off }}</span>
              / {{ project.checklist_total }} sign-offs
            </div>
          </div>
        </router-link>
      </div>
    </main>
  </div>
</template>

<script setup>
import { Button, createResource } from 'frappe-ui'
import AppHeader from '@/components/AppHeader.vue'
import ProgressRing from '@/components/ProgressRing.vue'
import { formatDate } from '@/utils/format'
import { toast, errorMessage } from '@/utils/toast'

const projects = createResource({
  url: 'agile_projects.api.get_projects',
  auto: true,
  onError(err) {
    toast({ title: 'Failed to load projects', text: errorMessage(err), type: 'error' })
  },
})

function projectStatusPill(status) {
  if (status === 'Completed') return 'bg-green-100 text-green-700'
  if (status === 'Cancelled') return 'bg-gray-100 text-gray-500'
  return 'bg-blue-100 text-blue-700'
}
</script>
