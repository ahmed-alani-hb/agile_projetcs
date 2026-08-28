import { createRouter, createWebHistory } from 'vue-router'
import { sessionUser } from '@/data/session'

const routes = [
  {
    path: '/',
    name: 'ProjectList',
    component: () => import('@/pages/ProjectList.vue'),
  },
  {
    path: '/projects/:projectId',
    name: 'ProjectBoard',
    component: () => import('@/pages/ProjectBoard.vue'),
    props: true,
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
