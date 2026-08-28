// Must stay in sync with AGILE_STATUSES in agile_projects/overrides/task.py.
// The board also receives the authoritative list from api.get_board.
export const STATUSES = ['Backlog', 'To Do', 'In Progress', 'QA/Code Review', 'Blocked', 'Done']

export const STATUS_META = {
  Backlog: {
    dot: 'bg-gray-400',
    pill: 'bg-gray-100 text-gray-700',
    column: 'border-gray-300',
  },
  'To Do': {
    dot: 'bg-blue-500',
    pill: 'bg-blue-100 text-blue-700',
    column: 'border-blue-400',
  },
  'In Progress': {
    dot: 'bg-orange-500',
    pill: 'bg-orange-100 text-orange-700',
    column: 'border-orange-400',
  },
  'QA/Code Review': {
    dot: 'bg-purple-500',
    pill: 'bg-purple-100 text-purple-700',
    column: 'border-purple-400',
  },
  Blocked: {
    dot: 'bg-red-500',
    pill: 'bg-red-100 text-red-700',
    column: 'border-red-400',
  },
  Done: {
    dot: 'bg-green-500',
    pill: 'bg-green-100 text-green-700',
    column: 'border-green-400',
  },
}

export const POINT_OPTIONS = ['1', '2', '3', '5', '8', '13']

export const POINT_COLORS = {
  1: 'bg-green-100 text-green-700',
  2: 'bg-teal-100 text-teal-700',
  3: 'bg-blue-100 text-blue-700',
  5: 'bg-purple-100 text-purple-700',
  8: 'bg-orange-100 text-orange-700',
  13: 'bg-red-100 text-red-700',
}

export const PRIORITIES = ['Low', 'Medium', 'High', 'Urgent']

export const PRIORITY_COLORS = {
  Low: 'text-gray-500',
  Medium: 'text-blue-600',
  High: 'text-orange-600',
  Urgent: 'text-red-600',
}

export const MODULES = [
  'Accounting',
  'Inventory',
  'CRM',
  'Selling',
  'Buying',
  'Manufacturing',
  'HR & Payroll',
  'Projects',
  'Assets',
  'Support',
  'Website',
  'Other',
]

export const PLATFORMS = ['Odoo', 'ERPNext']

export const PLATFORM_COLORS = {
  Odoo: 'bg-purple-100 text-purple-700',
  ERPNext: 'bg-blue-100 text-blue-700',
}

export const CONFIG_STATUSES = ['Not Started', 'In Progress', 'Configured', 'Verified']
export const MIGRATION_STATUSES = ['Not Started', 'In Progress', 'Migrated', 'Validated']
