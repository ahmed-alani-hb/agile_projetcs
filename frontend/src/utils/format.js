export function formatDate(value) {
  if (!value) return ''
  const date = new Date(value)
  if (isNaN(date)) return value
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function formatDateTime(value) {
  if (!value) return ''
  const date = new Date(String(value).replace(' ', 'T'))
  if (isNaN(date)) return value
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function isOverdue(value) {
  if (!value) return false
  const date = new Date(value)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return date < today
}

export function initials(name) {
  if (!name) return '?'
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join('')
}

export function formatHours(value) {
  const hours = parseFloat(value)
  if (!hours) return '0h'
  return Number.isInteger(hours) ? `${hours}h` : `${hours.toFixed(2)}h`
}
