// Frappe date fields are plain 'YYYY-MM-DD' strings; new Date() would parse
// them as UTC midnight, shifting the displayed day for users west of UTC.
function parseLocalDate(value) {
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [year, month, day] = value.split('-').map(Number)
    return new Date(year, month - 1, day)
  }
  return new Date(String(value).replace(' ', 'T'))
}

export function formatDate(value) {
  if (!value) return ''
  const date = parseLocalDate(value)
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
  const date = parseLocalDate(value)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return date < today
}

// Task.description is a Text Editor (HTML) field in ERPNext. The SPA edits it
// as plain text, so convert at the boundary in both directions. Rich
// formatting entered in Desk is flattened if the description is then edited
// from the SPA.
export function htmlToText(html) {
  if (!html) return ''
  const withBreaks = String(html)
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(p|div|li|h[1-6]|tr)>/gi, '\n')
  const el = document.createElement('div')
  el.innerHTML = withBreaks
  return (el.textContent || '').replace(/\n{3,}/g, '\n\n').trim()
}

export function textToHtml(text) {
  if (!text) return ''
  const el = document.createElement('div')
  el.textContent = text
  return el.innerHTML.replace(/\n/g, '<br>')
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

// ERPNext v16 made Task.exp_start_date / exp_end_date Datetime fields, so the
// API returns "YYYY-MM-DD HH:MM:SS". <input type="date"> only accepts
// "YYYY-MM-DD" and renders blank for anything else.
export function toDateInput(value) {
  if (!value) return ''
  return String(value).slice(0, 10)
}
