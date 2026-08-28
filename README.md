# Agile Projects

Agile project management for ERPNext — a standalone single-page application
(Vue 3 + Tailwind CSS + [Frappe UI](https://github.com/frappe/frappe-ui))
served at **`/agile`**, bypassing the Frappe Desk entirely while reading and
writing the standard ERPNext **Project**, **Task** and **Timesheet** doctypes.
Architecture mirrors Frappe CRM / Frappe HR.

Inspired by ClickUp, Jira, Asana, Smartsheet and Microsoft Project: a
drag-and-drop Kanban board, story-point badges, blocked-card highlighting,
WIP counts per column, SME avatars, quick-add, inline autosave, and a
slide-out task drawer.

## Features

### Five views over the same tasks (`/agile/projects/<project>/<view>`)

Switch between **Board · List · Table · Timeline · Calendar**. Filters (search,
status, SME, priority, overdue) apply across every view and can be stored as
per-user **saved views**.

- **List** — grouped by status, priority or SME with point subtotals.
- **Table** — spreadsheet-style: pick your columns, edit cells inline, and
  multi-select rows to **bulk change** status/priority/points. Each row is saved
  individually, so one task rejected by the dependency gate never silently
  discards the rest — you get a per-task report.
- **Timeline** — a Gantt (`frappe-gantt`) with drag-to-reschedule, dependency
  arrows and a **computed critical path**. Stock ERPNext's Gantt renders
  dependencies read-only and has no critical-path concept.
- **Calendar** — tasks on their due dates, colour-coded by status.
- **My Work** (`/agile/my-work`) — everything assigned to you across *all*
  projects, bucketed into Overdue / Blocked / Due today / This week / Later.

### Kanban board (`/agile/projects/<project>`)
- Six agile statuses replace ERPNext's standard Task statuses:
  **Backlog → To Do → In Progress → QA/Code Review → Blocked → Done**
- Drag-and-drop between columns (vuedraggable / SortableJS)
- **Strict dependency gate** (server-enforced): a task with entries in the
  standard *Task Depends On* table cannot move to **In Progress** or **Done**
  until every dependency is **Done** — the drop is rejected with a clear
  error toast and the card snaps back. The same rule applies in Desk, since
  it lives in the Task controller, not the UI.
- Complexity Points (1, 2, 3, 5, 8, 13) with per-column point totals
- Blocked cards get red styling and a tooltip listing the blocking tasks
- Filters: text search, SME, priority; per-column quick-add

### Task drawer
- Inline autosave of subject, priority, complexity points, SME Responsible
  (Link → Employee, distinct from owner), dates, progress
- Rich-text description (round-trips ERPNext's Text Editor HTML field)
- Dependency panel with live status — **add and remove dependencies here**;
  ERPNext offers no UI for this outside the Desk form's child table
- **ERP Module Readiness Checklist** tab: check off module sign-offs
- **Time** tab: log hours to standard ERPNext **Timesheets** (submitted, so
  hours roll into `Task.actual_time` and project costing)

### Project portfolio (`/agile`)
- Progress rings, done/total task counts, checklist sign-off counts

### ERP Module Readiness Checklist (custom child table on Project)
Per module (Accounting, Inventory, CRM, …): System Platform (**Odoo /
ERPNext**), Configuration Status, Data Migration Status, and a Functional
Sign-off checkbox. Also editable from Desk on the Project form.

### Project progress %
`Project.percent_complete` is computed server-side on every task/checklist
change: **70%** complexity-point-weighted task completion + **30%**
checklist sign-offs (weights in `agile_projects/progress.py`).

## Installation

Requires Frappe **v15/v16** with **ERPNext** installed on the site.

```bash
cd $BENCH
bench get-app https://github.com/ahmed-alani-hb/agile_projetcs
bench --site yoursite install-app agile_projects
bench build --app agile_projects
bench --site yoursite clear-cache
```

Open `https://yoursite/agile`. Users need one of the roles: **System
Manager**, **Projects Manager** or **Projects User**. Logging time requires
an active **Employee** record whose *User ID* is the logged-in user.

### What installation changes on the site
- Property Setters: `Task.status` options → the six agile statuses
  (existing tasks are migrated: Open→To Do, Working→In Progress,
  Pending Review→QA/Code Review, Overdue→To Do, Completed/Cancelled→Done,
  Template→Backlog)
- Custom fields: `Task.complexity_points`, `Task.sme_responsible`,
  `Project.erp_module_readiness` (Table → *ERP Module Readiness Checklist*)
- `override_doctype_class` for **Task** (`AgileTask`): dependency gate,
  Done→100% progress, completion stamps, dependent-task rescheduling keyed
  on Backlog/To Do, auto-start to In Progress on the first submitted
  timesheet (only when unblocked), and a no-op `update_status` so the daily
  "Overdue" scheduler cannot write an out-of-options status
- `override_doctype_class` for **Project** (`AgileProject`): percent and
  status derivation adapted to agile statuses (core would otherwise pin
  every project's status to "Open"); Completed at 100%, Manual method and
  Cancelled/On hold respected
- Doc events recompute `Project.percent_complete` (ERPNext's own
  calculation counts statuses that no longer exist)

Customizations are re-asserted on every `bench migrate`, so ERPNext
upgrades cannot strand them.

## Frontend development

```bash
cd apps/agile_projects/frontend
yarn install
yarn dev   # Vite dev server on :8080, proxying /api and /assets to the bench
```

For the dev server, enable developer mode and (for POST calls from the
Vite origin) set `"ignore_csrf": 1` in the site config. In production the
built `www/agile.html` receives the CSRF token via server-rendered boot
(`window.csrf_token`), which frappe-ui sends as `X-Frappe-CSRF-Token`.

`yarn build` (run automatically by `bench build`) outputs hashed assets to
`agile_projects/public/frontend/` and copies the built `index.html` to
`agile_projects/www/agile.html`. Both are gitignored build artifacts.

## API surface

All endpoints live in `agile_projects/api.py`, are whitelisted, go through
standard role/document permissions, and writes are POST-only:

| Endpoint | Purpose |
|---|---|
| `get_projects` | Portfolio cards with progress + counts |
| `get_board` | Tasks grouped by status, with batched blocker info |
| `update_task_status` | Status transition (dependency gate enforced) |
| `get_task` / `create_task` / `update_task` | Task detail CRUD (field allowlist) |
| `get_checklist` / `add_checklist_row` / `update_checklist_row` / `delete_checklist_row` | ERP readiness checklist |
| `log_time` / `get_task_timesheets` | ERPNext Timesheet logging per task |
| `get_employees` / `get_activity_types` / `get_user_info` | Pickers & header |

View endpoints live in `agile_projects/views.py`:

| Endpoint | Purpose |
|---|---|
| `get_project_meta` | Shared header payload |
| `get_tasks_list` | Paginated, filtered list — List, Table and Calendar |
| `bulk_update_tasks` | Multi-task edit with per-task success/failure reporting |
| `get_timeline` | Tasks + dependency edges + computed critical path |
| `update_task_dates` | Drag-to-reschedule from the Gantt |
| `set_task_dependency` / `remove_task_dependency` / `get_task_dependencies` | Editable dependency links |
| `reorder_column` | Persist board card order in the indexed `board_order` field |
| `get_my_work` | Cross-project assignments, bucketed |
| `get_views` / `save_view` / `delete_view` | Per-user saved views |

## Known limitations

- The Desk *Project → Set Status* action writes legacy Task statuses via a
  raw `db_set` that bypasses validation; such tasks self-heal to agile
  statuses on their next save.
- Uninstalling the app does not revert the status Property Setter or map
  statuses back to ERPNext defaults.
- Card order *within* a column is not persisted (drag between columns is a
  status change); a `kanban_order` field is a planned enhancement.

## License

MIT
