import { reactive } from 'vue'
import { createResource } from 'frappe-ui'

export function sessionUser() {
  const cookies = new URLSearchParams(document.cookie.split('; ').join('&'))
  let user = cookies.get('user_id')
  if (user === 'Guest') user = null
  return user
}

export const session = reactive({
  user: sessionUser(),
  get isLoggedIn() {
    return !!this.user
  },
})

export const logout = createResource({
  url: 'logout',
  onSuccess() {
    window.location.href = '/login?redirect-to=/agile'
  },
})

export const userInfo = createResource({
  url: 'agile_projects.api.get_user_info',
  cache: 'agile:user_info',
})
