"""Metrics: is this rollout going to make it?

The app could plan a rollout and enforce how it advanced, but not answer that
question. This module supplies the numbers behind the dashboards.

**On history, and being honest about it.** Some of this is computable
retroactively and some is not, and the difference is deliberate rather than
incidental:

- *Velocity, throughput, burn-up* work from day one, because
  `AgileTask.set_completion_fields` has always stamped `Task.completed_on`.
- *Lead time* likewise, from `creation` to `completed_on`.
- *Module gate history* works back to Phase 2, because `Agile Module` has
  carried `track_changes: 1` since it was created.
- *Per-status cycle time and cumulative flow* do **not** work retroactively:
  Task `Version` rows only begin at the Phase 3 migrate, with no backfill. They
  accumulate from `Agile Metric Snapshot` instead, and every flow payload
  carries `history_starts_on` so the UI can say "tracking since <date>" rather
  than draw a flat line through a past nobody recorded.

**One trap worth stating.** `api.log_time` synthesises `from_time`/`to_time` —
it backdates from now and shifts past the caller's last log to dodge ERPNext's
overlap validation. The *duration* is faithful; the *timestamps are not*. So
effort is aggregated per task, module and person, and never plotted against a
time axis.

Conventions match `agile_projects/modules.py`: `_ensure_app_access()` first,
then a per-document permission check. Aggregation follows `api.get_projects` —
one grouped query fanned across every row, then folded in Python.
"""

import json
from collections import defaultdict
from datetime import timedelta

import frappe
from frappe import _
from frappe.query_builder.functions import Count, Sum
from frappe.utils import add_days, cint, flt, getdate, nowdate

from agile_projects.agile_projects.doctype.agile_module.agile_module import (
    GATES,
    GATE_POSITION,
)
from agile_projects.api import _ensure_app_access
from agile_projects.modules import _check_project
from agile_projects.overrides.task import AGILE_STATUSES, DONE

BLOCKED = "Blocked"

# Task rows the whole app ignores: group headers and templates.
REAL_TASKS = {"is_group": 0, "is_template": 0}

DEFAULT_WINDOW_DAYS = 90
MAX_WINDOW_DAYS = 730


def _window(days):
    days = min(max(cint(days) or DEFAULT_WINDOW_DAYS, 7), MAX_WINDOW_DAYS)
    today = getdate(nowdate())
    return add_days(today, -days), today, days


# ---------------------------------------------------------------------------
# Pure helpers — no frappe, no database, unit-tested offline
# ---------------------------------------------------------------------------


def points_of(task):
    """Weight of a task in points.

    `complexity_points` is a Select of *strings*, and an unestimated task still
    has to move the needle — so an absent or unparseable value weighs 1. This
    matches progress.py and modules.py exactly; the three must not drift.
    """
    return cint(task.get("complexity_points")) or 1


def percentile(values, fraction):
    """Linear-interpolated percentile over an unsorted list.

    Returns None for an empty list rather than 0: "no data" and "zero days" are
    different answers and a dashboard must not confuse them.
    """
    numbers = sorted(float(v) for v in values if v is not None)
    if not numbers:
        return None
    if len(numbers) == 1:
        return numbers[0]
    position = max(0.0, min(1.0, float(fraction))) * (len(numbers) - 1)
    low = int(position)
    high = min(low + 1, len(numbers) - 1)
    weight = position - low
    return numbers[low] * (1 - weight) + numbers[high] * weight


def week_start(value):
    """The Monday of the value's week, as a date."""
    day = getdate(value)
    return day - timedelta(days=day.weekday())


def bucket_by_week(rows, date_key, weight=None, since=None, until=None):
    """Sum rows into consecutive Monday-anchored weeks.

    Emits every week in the range including empty ones — a velocity chart with
    gaps silently skipped reads as though nothing was ever missed.
    """
    totals = defaultdict(float)
    for row in rows:
        value = row.get(date_key)
        if not value:
            continue
        totals[week_start(value)] += float(weight(row)) if weight else 1.0

    if since is None or until is None:
        if not totals:
            return []
        since = since or min(totals)
        until = until or max(totals)

    cursor, last = week_start(since), week_start(until)
    series = []
    while cursor <= last:
        series.append({"week": str(cursor), "value": round(totals.get(cursor, 0.0), 2)})
        cursor += timedelta(days=7)
    return series


def lead_time_days(created, completed):
    """Whole days from creation to completion; None when either end is missing."""
    if not created or not completed:
        return None
    return max((getdate(completed) - getdate(created)).days, 0)


def velocity_from_completions(tasks, since, until):
    """Points completed per week, from `completed_on` — no snapshots required."""
    done = [
        task
        for task in tasks
        if task.get("completed_on") and since <= getdate(task["completed_on"]) <= until
    ]
    return bucket_by_week(done, "completed_on", weight=points_of, since=since, until=until)


def gate_history_from_versions(versions):
    """Gate transitions pulled out of `Version.data` payloads.

    `data.changed` is a list of `[fieldname, old, new]`; anything that is not a
    gate move, or moves to a gate we do not recognise, is skipped rather than
    guessed at. Returns `[{on, module, from, to}]` oldest first.
    """
    moves = []
    for version in versions:
        payload = version.get("data")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload or "{}")
            except (ValueError, TypeError):
                continue
        if not isinstance(payload, dict):
            continue
        for change in payload.get("changed") or []:
            if not isinstance(change, (list, tuple)) or len(change) < 3:
                continue
            field, old, new = change[0], change[1], change[2]
            if field != "gate" or new not in GATE_POSITION or old == new:
                continue
            moves.append(
                {
                    "on": str(getdate(version.get("creation"))),
                    "module": version.get("docname"),
                    "from": old,
                    "to": new,
                }
            )
    moves.sort(key=lambda move: move["on"])
    return moves


def summarise_counts(rows, key, vocabulary):
    """Counts keyed by a known vocabulary, in vocabulary order, zeroes included."""
    counts = {value: 0 for value in vocabulary}
    for row in rows:
        value = row.get(key)
        if value in counts:
            counts[value] += 1
    return [{"label": value, "value": counts[value]} for value in vocabulary]


# ---------------------------------------------------------------------------
# Shared fetches
# ---------------------------------------------------------------------------

# `completed_on` and `creation` are not in views.LIST_FIELDS; they are the two
# columns the retroactive metrics rest on.
METRIC_TASK_FIELDS = [
    "name",
    "status",
    "complexity_points",
    "expected_time",
    "actual_time",
    "agile_module",
    "exp_end_date",
    "completed_on",
    "creation",
]


def _project_tasks(project):
    return frappe.get_all(
        "Task",
        filters=dict(REAL_TASKS, project=project),
        fields=METRIC_TASK_FIELDS,
        limit_page_length=0,
    )


def _task_summary(tasks, since, until):
    """The parts of a project's metrics derived purely from its tasks."""
    total_points = sum(points_of(t) for t in tasks)
    done_points = sum(points_of(t) for t in tasks if t.status == DONE)
    lead_times = [
        lead_time_days(t.get("creation"), t.get("completed_on"))
        for t in tasks
        if t.status == DONE and t.get("completed_on")
    ]
    lead_times = [value for value in lead_times if value is not None]

    today = getdate(nowdate())
    overdue = [
        t
        for t in tasks
        if t.status != DONE and t.get("exp_end_date") and getdate(t["exp_end_date"]) < today
    ]

    return {
        "total_tasks": len(tasks),
        "done_tasks": sum(1 for t in tasks if t.status == DONE),
        "blocked_tasks": sum(1 for t in tasks if t.status == BLOCKED),
        "overdue_tasks": len(overdue),
        "total_points": total_points,
        "done_points": done_points,
        "status_mix": summarise_counts(tasks, "status", AGILE_STATUSES),
        "velocity": velocity_from_completions(tasks, since, until),
        "lead_time": {
            "count": len(lead_times),
            "median": percentile(lead_times, 0.5),
            "p85": percentile(lead_times, 0.85),
        },
    }


def _effort_rollup(project, tasks):
    """Logged hours against estimate, per module.

    Hours come from submitted Timesheet Details in one grouped query rather
    than `Task.actual_time`, so a task the sync or Desk touched is counted the
    same way. Deliberately *not* a time series — see the module docstring.
    """
    by_task = {t.name: t for t in tasks}
    if not by_task:
        return []

    detail = frappe.qb.DocType("Timesheet Detail")
    rows = (
        frappe.qb.from_(detail)
        .select(detail.task, Sum(detail.hours).as_("hours"))
        .where(detail.task.isin(list(by_task)) & (detail.docstatus == 1))
        .groupby(detail.task)
        .run(as_dict=True)
    )
    logged = {row.task: flt(row.hours) for row in rows}

    buckets = defaultdict(lambda: {"logged": 0.0, "estimated": 0.0, "tasks": 0})
    for name, task in by_task.items():
        key = task.get("agile_module") or ""
        bucket = buckets[key]
        bucket["logged"] += logged.get(name, 0.0)
        bucket["estimated"] += flt(task.get("expected_time"))
        bucket["tasks"] += 1

    labels = _module_labels(project)
    return [
        {
            "module": key or None,
            "label": labels.get(key, _("Unassigned")),
            "logged": round(value["logged"], 2),
            "estimated": round(value["estimated"], 2),
            "tasks": value["tasks"],
        }
        for key, value in sorted(buckets.items(), key=lambda item: -item[1]["logged"])
    ]


def _module_labels(project):
    return {
        row.name: row.module_name
        for row in frappe.get_all(
            "Agile Module", filters={"project": project}, fields=["name", "module_name"]
        )
    }


def _module_summary(project):
    modules = frappe.get_all(
        "Agile Module",
        filters={"project": project},
        fields=["name", "module_name", "gate", "target_go_live", "functional_signoff"],
        limit_page_length=0,
    )
    today = getdate(nowdate())
    at_risk = [
        {
            "name": m.name,
            "module_name": m.module_name,
            "gate": m.gate,
            "target_go_live": str(m.target_go_live),
            "days_late": (today - getdate(m.target_go_live)).days,
        }
        for m in modules
        if m.gate != "Live" and m.target_go_live and getdate(m.target_go_live) < today
    ]
    positions = [GATE_POSITION.get(m.gate, 0.0) for m in modules]

    next_go_live = min(
        (getdate(m.target_go_live) for m in modules if m.target_go_live and m.gate != "Live"),
        default=None,
    )

    return {
        "total": len(modules),
        "live": sum(1 for m in modules if m.gate == "Live"),
        "gate_mix": summarise_counts(modules, "gate", GATES),
        "readiness": round(sum(positions) / len(positions) * 100, 1) if positions else None,
        "at_risk": sorted(at_risk, key=lambda m: -m["days_late"]),
        "next_go_live": str(next_go_live) if next_go_live else None,
        "days_to_next_go_live": (next_go_live - today).days if next_go_live else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_project_metrics(project, days=DEFAULT_WINDOW_DAYS):
    _ensure_app_access()
    _check_project(project)
    since, until, days = _window(days)

    tasks = _project_tasks(project)
    meta = frappe.db.get_value(
        "Project",
        project,
        ["name", "project_name", "percent_complete", "expected_start_date", "expected_end_date"],
        as_dict=True,
    )

    return {
        "project": meta,
        "window_days": days,
        "tasks": _task_summary(tasks, since, until),
        "modules": _module_summary(project),
        "effort": _effort_rollup(project, tasks),
        "gate_moves": _gate_moves(project, since),
    }


def _gate_moves(project, since):
    """Gate transitions for this project's modules, oldest first.

    Available back to Phase 2 because `Agile Module` has always been versioned.
    """
    names = frappe.get_all("Agile Module", filters={"project": project}, pluck="name")
    if not names:
        return []
    versions = frappe.get_all(
        "Version",
        filters={
            "ref_doctype": "Agile Module",
            "docname": ["in", names],
            "creation": [">=", str(since)],
        },
        fields=["docname", "creation", "data"],
        order_by="creation asc",
        limit_page_length=0,
    )
    return gate_history_from_versions(versions)


@frappe.whitelist()
def get_flow_metrics(project, days=DEFAULT_WINDOW_DAYS):
    """Cumulative flow from daily snapshots.

    Returns `history_starts_on` so the caller can say how far back tracking
    actually goes instead of implying the series began at zero.
    """
    _ensure_app_access()
    _check_project(project)
    since, until, days = _window(days)

    rows = frappe.get_all(
        "Agile Metric Snapshot",
        filters={"project": project, "snapshot_date": [">=", str(since)]},
        fields=["snapshot_date", "status_counts", "total_points", "done_points"],
        order_by="snapshot_date asc",
        limit_page_length=0,
    )

    earliest = frappe.db.get_value(
        "Agile Metric Snapshot",
        {"project": project},
        "snapshot_date",
        order_by="snapshot_date asc",
    )

    flow = []
    for row in rows:
        try:
            counts = json.loads(row.status_counts or "{}")
        except (ValueError, TypeError):
            counts = {}
        entry = {"date": str(row.snapshot_date)}
        for status in AGILE_STATUSES:
            entry[status] = cint(counts.get(status))
        entry["done_points"] = flt(row.done_points)
        entry["total_points"] = flt(row.total_points)
        flow.append(entry)

    return {
        "flow": flow,
        "statuses": AGILE_STATUSES,
        "history_starts_on": str(earliest) if earliest else None,
        "window_days": days,
    }


@frappe.whitelist()
def get_portfolio_metrics():
    """The same picture across every project the user can see."""
    _ensure_app_access()

    # get_list applies the user's permissions; the aggregates below are then
    # scoped to the names it returned, matching api.get_projects.
    projects = frappe.get_list(
        "Project",
        fields=[
            "name",
            "project_name",
            "status",
            "percent_complete",
            "expected_start_date",
            "expected_end_date",
        ],
        order_by="expected_end_date asc",
        limit_page_length=0,
    )
    if not projects:
        return {"projects": [], "totals": {}, "at_risk": [], "gate_mix": []}

    names = [p.name for p in projects]
    today = getdate(nowdate())

    task_table = frappe.qb.DocType("Task")
    counts = (
        frappe.qb.from_(task_table)
        .select(task_table.project, task_table.status, Count(task_table.name).as_("count"))
        .where(
            task_table.project.isin(names)
            & (task_table.is_group == 0)
            & (task_table.is_template == 0)
        )
        .groupby(task_table.project, task_table.status)
        .run(as_dict=True)
    )

    by_project = defaultdict(lambda: {"total": 0, "done": 0, "blocked": 0})
    for row in counts:
        stats = by_project[row.project]
        stats["total"] += row.count
        if row.status == DONE:
            stats["done"] += row.count
        elif row.status == BLOCKED:
            stats["blocked"] += row.count

    modules = frappe.get_all(
        "Agile Module",
        filters={"project": ["in", names]},
        fields=["name", "project", "module_name", "gate", "target_go_live"],
        limit_page_length=0,
    )
    modules_by_project = defaultdict(list)
    for module in modules:
        modules_by_project[module.project].append(module)

    at_risk = [
        {
            "project": m.project,
            "module": m.name,
            "module_name": m.module_name,
            "gate": m.gate,
            "target_go_live": str(m.target_go_live),
            "days_late": (today - getdate(m.target_go_live)).days,
        }
        for m in modules
        if m.gate != "Live" and m.target_go_live and getdate(m.target_go_live) < today
    ]

    for project in projects:
        stats = by_project.get(project.name, {"total": 0, "done": 0, "blocked": 0})
        own = modules_by_project.get(project.name, [])
        go_lives = [getdate(m.target_go_live) for m in own if m.target_go_live and m.gate != "Live"]
        project.update(
            {
                "total_tasks": stats["total"],
                "done_tasks": stats["done"],
                "blocked_tasks": stats["blocked"],
                "module_total": len(own),
                "module_live": sum(1 for m in own if m.gate == "Live"),
                "next_go_live": str(min(go_lives)) if go_lives else None,
            }
        )

    return {
        "projects": projects,
        "totals": {
            "projects": len(projects),
            "total_tasks": sum(p["total_tasks"] for p in projects),
            "done_tasks": sum(p["done_tasks"] for p in projects),
            "blocked_tasks": sum(p["blocked_tasks"] for p in projects),
            "modules": len(modules),
            "modules_live": sum(1 for m in modules if m.gate == "Live"),
            "modules_at_risk": len(at_risk),
        },
        "gate_mix": summarise_counts(modules, "gate", GATES),
        "at_risk": sorted(at_risk, key=lambda m: -m["days_late"]),
    }


# ---------------------------------------------------------------------------
# The daily snapshot — the only way per-status flow can ever exist
# ---------------------------------------------------------------------------


def snapshot_project(project, on_date=None):
    """Write (or rewrite) one project's snapshot for a day.

    Idempotent by (project, snapshot_date): running it twice updates the row
    rather than adding a second, so a manual re-run after a fix is safe.
    """
    on_date = getdate(on_date or nowdate())
    tasks = _project_tasks(project)
    modules = frappe.get_all(
        "Agile Module", filters={"project": project}, fields=["gate"], limit_page_length=0
    )

    status_counts = {status: 0 for status in AGILE_STATUSES}
    for task in tasks:
        if task.status in status_counts:
            status_counts[task.status] += 1

    gate_counts = {gate: 0 for gate in GATES}
    for module in modules:
        if module.gate in gate_counts:
            gate_counts[module.gate] += 1

    values = {
        "total_tasks": len(tasks),
        "done_tasks": sum(1 for t in tasks if t.status == DONE),
        "blocked_tasks": sum(1 for t in tasks if t.status == BLOCKED),
        "total_points": sum(points_of(t) for t in tasks),
        "done_points": sum(points_of(t) for t in tasks if t.status == DONE),
        "modules_total": len(modules),
        "modules_live": sum(1 for m in modules if m.gate == "Live"),
        "percent_complete": flt(frappe.db.get_value("Project", project, "percent_complete")),
        "status_counts": json.dumps(status_counts),
        "gate_counts": json.dumps(gate_counts),
    }

    existing = frappe.db.exists(
        "Agile Metric Snapshot", {"project": project, "snapshot_date": on_date}
    )
    if existing:
        doc = frappe.get_doc("Agile Metric Snapshot", existing)
        doc.update(values)
        doc.save(ignore_permissions=True)
        return doc.name

    doc = frappe.get_doc(
        dict(doctype="Agile Metric Snapshot", project=project, snapshot_date=on_date, **values)
    )
    doc.insert(ignore_permissions=True)
    return doc.name


def snapshot_all_projects():
    """Scheduled daily. One bad project must not starve the rest."""
    for project in frappe.get_all("Project", pluck="name"):
        try:
            snapshot_project(project)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title=f"Agile metric snapshot failed: {project}",
                message="Snapshot raised; continuing with the remaining projects.",
            )


@frappe.whitelist(methods=["POST"])
def take_snapshot_now(project):
    """Manual trigger, so a dashboard is not blank until tomorrow."""
    _ensure_app_access()
    _check_project(project, ptype="write")
    return {"snapshot": snapshot_project(project)}
