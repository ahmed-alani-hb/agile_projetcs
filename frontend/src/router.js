import { createRouter, createWebHistory } from 'vue-router'
import { sessionUser } from '@/data/session'

const VIEW_TYPES = [
  'board',
  'list',
  'table',
  'timeline',
  'calendar',
  'sheet',
  'modules',
  'cutover',
]

const routes = [
  {
    path: '/',
    name: 'ProjectList',
    component: () => import('@/pages/ProjectList.vue'),
  },
  {
    path: '/my-work',
    name: 'MyWork',
    component: () => import('@/pages/MyWork.vue'),
  },
  {
    path: '/projects/:projectId/:view?',
    name: 'ProjectDetail',
    component: () => import('@/pages/ProjectDetail.vue'),
    props: (route) => ({
      projectId: route.params.projectId,
      view: VIEW_TYPES.includes(route.params.view) ? route.params.view : 'board',
    }),
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
]

const router = createRouter({
  history: createWebHistory('/agile'),
  routes,
})

router.beforeEach((to, from, next) => {
  if (!sessionUser()) {
    window.location.href = `/login?redirect-to=${encodeURIComponent('/agile' + to.fullPath)}`
    return
  }
  next()
})

export default router
