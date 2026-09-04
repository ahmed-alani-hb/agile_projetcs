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

### Module gates — the delivery spine (`/agile/projects/<project>/modules`)

Stock ERPNext has no concept of an ERP module, so a rollout is planned as an
undifferentiated pile of tasks. Here a module is a first-class document with a
**phase gate** it has to earn its way through:

**Configure → Migrate → UAT → Sign-off → Live**

Drag a card between columns to move its gate. Three rules are **enforced on the
server**, in the `Agile Module` controller — so they hold in Desk as well as
the SPA:

| Moving to | Refused unless |
|---|---|
| **UAT** | the data migration is *Migrated* or *Validated* |
| **Sign-off** | every task linked to the module is *Done* |
| **Live** | *Functional Sign-off* is ticked |

A move is checked at **every gate it passes through**, so dragging a card from
Configure straight to Live is not a shortcut past UAT. Moving a module
*backwards* is always allowed — a correction should never be trapped. Each
refusal names the blocking gate, the reason, and the fix.

Open **blocked** tasks are deliberately *not* a gate: they show as a red count
on the card, because a hard block there would fire too often to respect.

Tasks roll up to a module through a new `agile_module` link, so every task view
can filter by module and a module card shows its own point-weighted progress.

### The cutover runbook (`/agile/projects/<project>/cutover`)

Cutover is the riskiest hour of a rollout and the one nobody wants to
improvise. An ordered runbook of **Cutover Steps**: owner, planned vs actual
times, a live elapsed clock, and a `depends_on` link enforced on completion
(not on start, so a step can be prepared early). Steps are started, completed,
skipped, failed and signed off — each stamping who and when.

### Discussion, assignment and evidence

Built on Frappe's own primitives, so everything written from the SPA is visible
in Desk and vice versa.

- **Comments with @mentions** on tasks and modules. Mentioning someone notifies
  them — but only if they can already read the document; a notification into a
  document you cannot open is both useless and a leak of its subject.
- **Assignment** (Frappe `ToDo`) with avatars on board cards and a picker in the
  task drawer. This is distinct from *SME Responsible*: a module has one owner,
  a task can have several people doing it. Assigned tasks appear in the
  assignee's **My Work** — which previously filtered on assignments the UI had
  no way to create.
- **Attachments**, stored **private** (`is_private=1`), so a UAT screenshot is
  not readable by anyone who guesses the URL.
- **Activity timeline** merging field changes (Frappe `Version`) and comments
  into one story: *"changed status from To Do to In Progress"*. Installation
  turns on `track_changes` for Task, which ERPNext leaves off.
- **Notification bell** in the header, with an unread count.

Comment bodies are rich text rendered with `v-html`, so they are sanitised on
write by `collaboration.clean_comment_html`. That does two things rather than
one: `frappe.utils.sanitize_html` returns its input **untouched** when the body
happens to parse as JSON, so dangerous elements are stripped outright first and
`always_sanitize=True` is passed to close the short-circuit.

Every endpoint taking a `(doctype, name)` pair from the client checks it
against an allowlist (`Task`, `Agile Module`, `Cutover Step`, `Project`)
*before* the permission check — otherwise reading comments would be a read
primitive over every doctype on the site.

### Live updates, and what happens when they aren't

The notification bell and open comment threads update over Frappe's socket.io.
Realtime is deliberately **not** wired to the boards: card positions still
refresh explicitly, which keeps paginated views from losing loaded pages.

Realtime is also the one part that can silently do nothing in production —
frappe-ui's `initSocket` always dials HTTPS on the site origin, so it needs
nginx proxying `/socket.io` and breaks outright on an HTTP-only site. Rather
than let the feature die quietly, `frontend/src/data/socket.js` watches the
connection and **falls back to polling** (20s) when it never arrives, and
refetches whenever the tab regains focus regardless of transport.

### Metrics (`/agile/projects/<project>/dashboard`) and the portfolio (`/agile/portfolio`)

Velocity, lead time, status and gate mix, effort against estimate, modules past
their go-live, and cumulative flow. Charts use echarts through frappe-ui — no
new dependency, it was already installed.

**What can and cannot be known.** Velocity, throughput and lead time are
computed from `Task.completed_on`, which has always been stamped on completion,
so they work on the first load rather than after a month of collecting. Module
gate history comes from `Version` rows, available since modules were
introduced. Per-status **flow** genuinely cannot be reconstructed — Task
versioning only began in the collaboration release — so an `Agile Metric
Snapshot` is written daily and the flow chart states the date its history
actually begins instead of drawing a line back through nothing.

Effort is aggregated per module and person, never over time: `log_time`
synthesises its from/to window to avoid ERPNext's overlap validation, so the
duration is trustworthy and the timestamps are not.

The chart palette was validated rather than eyeballed, and that changed the
design. The board's status colours fail in a chart — gray reads as "no data",
and Blocked against Done measures ΔE 7.4 for deuteranopes while sitting
adjacent in a stack. Since one hue cannot separate six adjacent bands, the flow
chart collapses to the four states a rollout steers on, and the full six-status
split is a bar chart where whitespace and labels carry identity.

### The roadmap Gantt (`/agile/projects/<project>/roadmap`)

Modules and cutover steps on one timeline: each module runs to its target
go-live, each cutover step shows planned against actual. A module has no start
date of its own, so its bar begins at the earliest start among its tasks — and
says so when it had to fall back to the project start, because a chart that
quietly invents dates is worse than one that admits to it.

### Nine views over the same tasks (`/agile/projects/<project>/<view>`)

Switch between **Board · List · Table · Timeline · Calendar · Modules ·
Cutover · Metrics · Roadmap**. Filters (search, status, SME, priority, overdue) apply across every
task view and can be stored as per-user **saved views**.

- **List** — grouped by status, priority or SME with point subtotals.
- **Table** — spreadsheet-style: pick your columns, edit cells inline, and
  multi-select rows to **bulk change** status/priority/points. Each row is saved
  individually, so one task rejected by the dependency gate never silently
  discards the rest — you get a per-task report.
- **Timeline** — a Gantt (`frappe-gantt`) with drag-to-reschedule, dependency
  arrows and a **computed critical path** that is recomputed after every drag.
  Also milestones, an actual-vs-planned rule inside each bar, and PNG export —
  none of which the library supports natively, so all three are drawn after it
  renders and degrade to a plain bar if they fail. Stock ERPNext's Gantt
  renders dependencies read-only and has no critical-path concept.
- **Calendar** — tasks on their due dates, colour-coded by status.
- **My Work** (`/agile/my-work`) — everything assigned to you across *all*
  projects, bucketed into Overdue / Blocked / Due today / This week / Later.

### Google Sheets sync (`/agile/projects/<project>/sheet`)

Mirror a project's tasks into a Google Sheet, and optionally let people who
never log into ERPNext edit them there.

- **Push** — the Sheet is a read-only mirror, refreshed on a schedule.
- **Two-way** — edits in the Sheet are written back through the normal
  document save path, so **permissions and the dependency gate still apply**.
  A blocked task rejected by the gate is reported per row; the rest of the
  batch still applies.

Safety, because a spreadsheet is a hostile input surface:

| Rail | Why |
|---|---|
| Every change logged with its **old value** | A bad paste is recoverable by inspection, not a DB restore |
| **Circuit breaker** (default 25 rows) | A runaway fill-drag halts the sync with nothing written |
| **Preview changes** | Full diff before anything is applied |
| **Never deletes** | A row removed from the Sheet re-appears on the next push; the Task survives |
| **Validate, never coerce** | A bad status/points/date is rejected with a reason, not silently mangled |
| Runs as a **named user**, never Administrator | Otherwise a scheduled job would bypass document permissions |

Identity is the **Task ID in column A** (protected), never the row number, so
people can insert, delete and sort rows freely. `description` is pushed
read-only — it is a rich-text field and a spreadsheet round-trip would flatten
it on every sync.

**Setup** — one Google Cloud project, one service account, no per-user login:

1. Enable the **Sheets API** and **Drive API** on a Google Cloud project.
2. Create a service account and download its JSON key.
3. Paste the key into **Agile Google Settings** (stored encrypted) and enable.
4. **Create each spreadsheet yourself**, then share it with the service account
   address as **Editor**. The app never creates spreadsheets — files owned by a
   service account belong to an identity nobody can sign into.

Until a key is configured the whole feature is inert. Note that the Sheet opens
in Google rather than embedding: Google does not permit framing the editable
Sheets UI on another domain, and the only embeddable form is public and
read-only.

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
- **Module** picker: roll the task up to an Agile Module, so it counts
  towards that module's Sign-off gate
- **Assigned to**: add and remove assignees; they appear on the board card
- **Discussion** tab: comments with @mentions, plus attachments
- **Activity** tab: field changes and comments in one timeline
- **ERP Checklist** tab: the superseded readiness grid, now read-only
- **Time** tab: log hours to standard ERPNext **Timesheets** (submitted, so
  hours roll into `Task.actual_time` and project costing)

### Project portfolio (`/agile`)
- Progress rings, done/total task counts, and modules-live counts (falling back
  to checklist sign-offs for a project with no modules yet)

### ERP Module Readiness Checklist (superseded, frozen)
The original child table on Project. Every row is migrated to an `Agile Module`
on upgrade; the grid stays visible but **read-only for one release** as the
rollback path. Removing one line from `PROPERTY_SETTERS` thaws it.

### Project progress %
`Project.percent_complete` is computed server-side on every task or gate
change: **70%** complexity-point-weighted task completion + **30%** module
readiness (weights in `agile_projects/progress.py`).

Readiness is **gate position**, not a checkbox — `Configure 0 · Migrate 0.25 ·
UAT 0.5 · Sign-off 0.75 · Live 1.0` — so a module that is migrated and in UAT
scores 50% where the old binary sign-off scored it 0. A project with no modules
yet still scores off its legacy checklist rows.

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
  `Task.agile_module` (Link → *Agile Module*),
  `Project.erp_module_readiness` (Table → *ERP Module Readiness Checklist*,
  now read-only)
- New doctypes: **Agile Module** (gates) and **Cutover Step** (runbook)
- A `[post_model_sync]` patch creates one Agile Module per existing checklist
  row, deriving the gate conservatively from what the row can evidence and
  **never** deriving *Live*. It is idempotent per (project, module), additive,
  and changes no existing row
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
- Property Setter turning on `track_changes` for **Task**, so the activity
  timeline has `Version` records to read

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

## Tests

```bash
bench --site yoursite run-tests --app agile_projects
```

`agile_projects/tests/test_gates.py` covers the gate model, the migration's
derivation ladder and progress blending as pure functions (no database).
`test_agile_module.py` exercises the three gate rules against real documents.
`test_metrics.py` covers the metric arithmetic — including that an unestimated
task weighs one point rather than zero, and that "no data" stays `None` rather
than becoming a misleading `0`. `test_wiring.py` guards agreements no single
file can enforce: the view-type list that lives in four places, that every
endpoint the SPA calls exists, and that the chart palette keeps its validated
values. `test_collaboration.py` pins the @mention parser against the exact HTML the
editor emits, the activity formatter, and — most importantly — that a comment
body which parses as JSON is still sanitised.

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

Module gates and cutover live in `agile_projects/modules.py`:

| Endpoint | Purpose |
|---|---|
| `get_modules` | Modules grouped into gate columns, with batched task rollup |
| `update_module_gate` | The enforced gate transition |
| `create_module` / `update_module` / `delete_module` | Module CRUD (field allowlist) |
| `reorder_gate` | Persist card order within a gate column |
| `get_cutover` / `add_cutover_step` / `update_cutover_step` / `delete_cutover_step` | Runbook CRUD |
| `start_step` / `complete_step` / `signoff_step` | Runbook execution, stamping actual times |
| `reorder_cutover` | Re-sequence the runbook |
| `get_roadmap` | Modules and cutover steps as Gantt bars |

Metrics live in `agile_projects/metrics.py`:

| Endpoint | Purpose |
|---|---|
| `get_project_metrics` | Velocity, lead time, status/gate mix, effort, at-risk modules |
| `get_flow_metrics` | Cumulative flow from snapshots, with its true start date |
| `get_portfolio_metrics` | The same across every visible project |
| `take_snapshot_now` | Start the flow series without waiting for the nightly job |

Collaboration lives in `agile_projects/collaboration.py`:

| Endpoint | Purpose |
|---|---|
| `get_comments` / `add_comment` / `delete_comment` | Discussion, with @mention notifications |
| `assign_task` / `unassign_task` / `get_assignees` | Frappe assignment from the SPA |
| `get_attachments` / `delete_attachment` | Files (uploads go through Frappe's own `upload_file`) |
| `get_activity` | Field changes and comments as one timeline |
| `get_notifications` / `mark_notification_read` / `mark_all_notifications_read` | The header bell |
| `get_mentionable_users` | Users with app access — the source for @mentions and assignment |

## Known limitations

- The Desk *Project → Set Status* action writes legacy Task statuses via a
  raw `db_set` that bypasses validation; such tasks self-heal to agile
  statuses on their next save.
- Uninstalling the app does not revert the status Property Setter or map
  statuses back to ERPNext defaults.
- The legacy readiness checklist is frozen, not removed. Uninstalling does not
  restore it to editable — drop the `Project-erp_module_readiness-read_only`
  Property Setter.
- A module's gate is not derived from its tasks; someone has to move it. That
  is deliberate — a gate is an assertion, not a calculation.
- A comment written in **Desk** does not push to an open SPA thread; it appears
  on the next fetch. Publishing from a `Comment` doc_event would fix that at
  the cost of firing site-wide for every Like and Info comment.
- Boards do not live-sync. Someone else's card move shows on your next refresh.
- Cumulative flow starts the day the snapshot job first runs; there is no
  backfill, because the data to backfill from was never recorded.
- Milestones, baselines and PNG export are drawn on top of `frappe-gantt`
  rather than by it. A library upgrade could break them; each fails to a plain
  bar rather than an empty chart.
- Snapshot rows accumulate at one per project per day and are never purged.
- @mentions and assignment list **users with an app role**, not employees.
  `Employee.user_id` is optional in ERPNext and usually blank, so sourcing them
  from Employee silently hid most people. *SME Responsible* is still a genuine
  Link → Employee and is unaffected.

## License

MIT
