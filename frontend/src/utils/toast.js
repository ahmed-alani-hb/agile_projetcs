import { reactive } from 'vue'

let nextId = 0

export const toasts = reactive([])

export function toast({ title, text = '', type = 'info', timeout = 5000 }) {
  const item = { id: ++nextId, title, text, type }
  toasts.push(item)
  if (timeout) {
    setTimeout(() => dismissToast(item.id), timeout)
  }
  return item.id
}

export function dismissToast(id) {
  const index = toasts.findIndex((t) => t.id === id)
  if (index > -1) toasts.splice(index, 1)
}

export function errorMessage(err, fallback = 'Something went wrong') {
  let message =
    (err?.messages?.length && err.messages.join('\n')) || err?.message || fallback
  return String(message).replace(/<[^>]*>/g, '')
}
