"""Endpoints backing the non-board views: List, Table, Timeline, Calendar,
My Work, and per-user saved views.

Everything reads through `frappe.get_list` and writes through `frappe.get_doc`
so standard permissions apply, and every aggregate uses the query builder —
recent Frappe rejects SQL functions passed as strings in a `fields` list.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, get_datetime, getdate, nowdate

from agile_projects.api import (
    TASK_EDITABLE_FIELDS,
    _attach_employee_info,
    _ensure_app_access,
    _get_blockers,
    normalize_task_dates,
)
from agile_projects.overrides.task import AGILE_STATUSES, DONE

LIST_FIELDS = [
    "name",
    "subject",
    "status",
    "priority",
    "complexity_points",
    "sme_responsible",
    "exp_start_date",
    "exp_end_date",
    "progress",
    "actual_time",
    "expected_time",
    "board_order",
    "project",
    "modified",
]

# Fields a user may change from the table view / bulk editor. `status` is
# included but still passes through AgileTask.validate_status, so the
# dependency gate holds.
BULK_EDITABLE_FIELDS = TASK_EDITABLE_FIELDS | {"status", "blocked_reason"}

VIEW_TYPES = ("board", "list", "table", "timeline", "calendar", "sheet")


# ---------------------------------------------------------------------------
# Shared filter handling
# ---------------------------------------------------------------------------


def _day_start(value):
    """00:00:00 on the given day, for the v16 Datetime exp_start_date."""
    return f"{getdate(value)} 00:00:00"


def _day_end_str(value):
    return f"{getdate(value)} 23:59:59.999999"


def _day_end(value):
    """23:59:59 on the given day, for the v16 Datetime exp_end_date."""
    return f"{getdate(value)} 23:59:59"


def _build_filters(project=None, filters=None):
    """Translate the SPA's filter object into get_list filters/or_filters."""
    filters = frappe.parse_json(filters) if filters else {}
    out = {"is_template": 0, "is_group": 0}
    or_filters = None

    if project:
        out["project"] = project

    status = filters.get("status")
    if status:
        out["status"] = ["in", status] if isinstance(status, (list, tuple)) else status

    for field in ("priority", "sme_responsible"):
        value = filters.get(field)
        if value:
            out[field] = ["in", value] if isinstance(value, (list, tuple)) else value

    points = filters.get("complexity_points")
    if points:
        out["complexity_points"] = ["in", points] if isinstance(points, (list, tuple)) else points

    # Date bounds are collected first and combined, so an `overdue` flag
    # narrows the user's date range instead of replacing it.
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    if filters.get("overdue"):
        today = nowdate()
        to_date = min(to_date, today) if to_date else today
        if "status" in out:
            # keep the explicit status filter; only exclude Done when the user
            # did not ask for a specific status
            if out["status"] == DONE:
                # "overdue AND Done" cannot match — return an impossible filter
                out["name"] = ["is", "not set"]
        else:
            out["status"] = ["!=", DONE]

    if from_date and to_date:
        # same midnight-truncation as the single-bound branch below: a bare
        # to_date against a Datetime column excludes that whole day's tasks
        out["exp_end_date"] = ["between", [from_date, _day_end_str(to_date)]]
    elif from_date:
        out["exp_end_date"] = [">=", from_date]
    elif to_date:
        # exp_end_date is Datetime on v16, and db_query formats a bare date as
        # midnight — so "<=" would drop everything due later that same day.
        out["exp_end_date"] = (
            ["<", to_date] if filters.get("overdue") else ["<=", _day_end_str(to_date)]
        )

    search = (filters.get("search") or "").strip()
    if search:
        or_filters = [
            ["Task", "subject", "like", f"%{search}%"],
            ["Task", "name", "like", f"%{search}%"],
        ]

    return out, or_filters


def _decorate(tasks):
    """Attach SME display info and blocker state to a list of task rows."""
    if not tasks:
        return tasks
    _attach_employee_info(tasks)
    blockers = _get_blockers([t.name for t in tasks])
    for task in tasks:
        task["blocked_by"] = blockers.get(task.name, [])
        task["is_blocked"] = task.status != DONE and any(
            dep["status"] != DONE for dep in task["blocked_by"]
        )
    return tasks


# ---------------------------------------------------------------------------
# List / Table / Calendar
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_project_meta(project):
    """Lightweight header payload shared by every view."""
    _ensure_app_access()
    frappe.has_permission("Project", doc=project, throw=True)
    meta = frappe.db.get_value(
        "Project",
        project,
        ["name", "project_name", "status", "percent_complete", "expected_end_date"],
        as_dict=True,
    )
    if not meta:
        frappe.throw(_("Project {0} not found").format(project), frappe.DoesNotExistError)
    return meta


@frappe.whitelist()
def get_tasks_list(
    project=None,
    filters=None,
    order_by="modified desc",
    start=0,
    page_length=100,
    fields=None,
):
    """Flat, paginated task list — powers the List, Table and Calendar views."""
    _ensure_app_access()
    if project:
        frappe.has_permission("Project", doc=project, throw=True)

    query_filters, or_filters = _build_filters(project, filters)

    requested = frappe.parse_json(fields) if fields else None
    if requested:
        # never trust client field names; intersect with the known-safe set
        select_fields = [f for f in requested if f in LIST_FIELDS] or list(LIST_FIELDS)
        for required in ("name", "status", "subject"):
            if required not in select_fields:
                select_fields.append(required)
    else:
        select_fields = list(LIST_FIELDS)

    start = cint(start)
    limit = cint(page_length) or 100

    # Fetch one extra row to learn whether another page exists, instead of
    # counting the whole table on every request.
    tasks = frappe.get_list(
        "Task",
        filters=query_filters,
        or_filters=or_filters,
        fields=select_fields,
        order_by=_safe_order_by(order_by),
        start=start,
        page_length=limit + 1,
    )
    has_more = len(tasks) > limit
    tasks = tasks[:limit]
    _decorate(tasks)

    return {"tasks": tasks, "has_more": has_more, "start": start}


def _safe_order_by(order_by):
    """Only allow `<known field> asc|desc` so the client can't inject SQL.

    A `name` tiebreaker is always appended: offset pagination over a
    non-unique key (exp_end_date, modified) otherwise duplicates and drops
    rows between pages.
    """
    tiebreak = "`tabTask`.`name` asc"
    if not order_by:
        return f"`tabTask`.`modified` desc, {tiebreak}"
    parts = str(order_by).strip().split()
    field = parts[0]
    direction = parts[1].lower() if len(parts) > 1 else "asc"
    if field not in LIST_FIELDS or direction not in ("asc", "desc"):
        return f"`tabTask`.`modified` desc, {tiebreak}"
    if field == "name":
        return f"`tabTask`.`name` {direction}"
    return f"`tabTask`.`{field}` {direction}, {tiebreak}"


@frappe.whitelist(methods=["POST"])
def bulk_update_tasks(tasks, fields):
    """Apply the same field changes to many tasks, reporting per-task failures.

    Each task is saved individually so document permissions and the agile
    dependency gate still apply; one rejected task does not abort the rest.
    """
    _ensure_app_access()
    tasks = frappe.parse_json(tasks) or []
    fields = frappe.parse_json(fields) or {}

    invalid = set(fields) - BULK_EDITABLE_FIELDS
    if invalid:
        frappe.throw(
            _("Field(s) {0} cannot be bulk edited").format(", ".join(sorted(invalid)))
        )
    if not tasks:
        frappe.throw(_("No tasks selected"))
    if fields.get("status") and fields["status"] not in AGILE_STATUSES:
        frappe.throw(_("Invalid status: {0}").format(fields["status"]))

    updated, failed = [], []
    for name in tasks:
        savepoint = f"bulk_{frappe.generate_hash(length=8)}"
        try:
            frappe.db.savepoint(savepoint)
            doc = frappe.get_doc("Task", name)
            # exp_* are Datetime on v16; a bare date string would be stored as
            # midnight (and an end date would land before its own day's work)
            doc.update(normalize_task_dates(dict(fields)))
            doc.save()
            updated.append(name)
        except Exception as exc:
            frappe.db.rollback(save_point=savepoint)
            failed.append({"task": name, "error": _clean_error(exc)})
    return {"updated": updated, "failed": failed}


def _clean_error(exc):
    """Human-readable reason for a per-task failure.

    frappe.throw stashes the text in frappe.message_log rather than on the
    exception, and PermissionError often stringifies to nothing at all.
    """
    message = getattr(exc, "message", None) or str(exc)
    if not str(message).strip():
        # frappe.get_message_log() was removed in v16; the underlying local
        # proxy still holds the same list of dicts.
        log = list(getattr(frappe.local, "message_log", None) or [])
        if log:
            last = log[-1]
            message = last.get("message") if isinstance(last, dict) else str(last)
    message = frappe.utils.strip_html(str(message or "")).strip()
    return message or _("Not permitted")


# ---------------------------------------------------------------------------
# Timeline (Gantt) — including critical path, which stock ERPNext lacks
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_timeline(project, filters=None):
    """Tasks + dependency edges + critical path for the timeline view."""
    _ensure_app_access()
    frappe.has_permission("Project", doc=project, throw=True)

    query_filters, or_filters = _build_filters(project, filters)
    tasks = frappe.get_list(
        "Task",
        filters=query_filters,
        or_filters=or_filters,
        fields=LIST_FIELDS + ["is_milestone"],
        order_by="exp_start_date asc, creation asc",
        limit_page_length=0,
    )
    _decorate(tasks)

    edges = _dependency_edges([t.name for t in tasks])
    for task in tasks:
        task["depends_on"] = edges.get(task.name, [])

    critical = compute_critical_path(tasks, edges)
    for task in tasks:
        task["is_critical"] = task.name in critical

    return {
        "tasks": tasks,
        "critical_path": sorted(critical),
        "project": frappe.db.get_value(
            "Project", project, ["name", "project_name", "percent_complete"], as_dict=True
        ),
    }


def _dependency_edges(task_names):
    """{task: [predecessor, ...]} limited to tasks inside the current set."""
    if not task_names:
        return {}
    rows = frappe.get_all(
        "Task Depends On",
        filters={"parenttype": "Task", "parent": ["in", task_names]},
        fields=["parent", "task"],
    )
    allowed = set(task_names)
    edges = {}
    for row in rows:
        if row.task and row.task in allowed:
            edges.setdefault(row.parent, []).append(row.task)
    return edges


def _duration_days(task):
    if task.get("exp_start_date") and task.get("exp_end_date"):
        return max(date_diff(task["exp_end_date"], task["exp_start_date"]) + 1, 1)
    if task.get("expected_time"):
        # expected_time is in hours; round up to whole days
        return max(int((flt(task["expected_time"]) + 7) // 8), 1)
    return 1


def compute_critical_path(tasks, edges):
    """Classic CPM forward/backward pass over the dependency DAG.

    Anchored to real calendar dates: a task starts no earlier than its own
    scheduled `exp_start_date`, so the result matches the chart the bars are
    drawn on. Only dated tasks participate — undated ones are not rendered on
    the timeline and must not shift the computed finish date. Returns the set
    of zero-slack task names; cycles yield an empty set (ERPNext blocks them
    via check_recursion anyway).
    """
    dated = [t for t in tasks if t.get("exp_start_date") and t.get("exp_end_date")]
    by_name = {t["name"]: t for t in dated}
    if not by_name:
        return set()

    origin = min(getdate(t["exp_start_date"]) for t in dated)
    fixed_start = {
        n: date_diff(getdate(by_name[n]["exp_start_date"]), origin) for n in by_name
    }

    preds = {name: [p for p in edges.get(name, []) if p in by_name] for name in by_name}
    succs = {name: [] for name in by_name}
    for name, plist in preds.items():
        for p in plist:
            succs[p].append(name)

    # Kahn topological order
    indegree = {name: len(preds[name]) for name in by_name}
    queue = [n for n, d in indegree.items() if d == 0]
    order = []
    while queue:
        node = queue.pop(0)
        order.append(node)
        for nxt in succs[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    if len(order) != len(by_name):
        # cyclic graph — cannot compute a meaningful critical path
        return set()

    duration = {n: _duration_days(by_name[n]) for n in by_name}
    earliest_start, earliest_finish = {}, {}
    for node in order:
        # a task cannot start before its own scheduled start, nor before its
        # predecessors finish
        start = max(
            [earliest_finish[p] for p in preds[node]] + [fixed_start[node]]
        )
        earliest_start[node] = start
        earliest_finish[node] = start + duration[node]

    project_end = max(earliest_finish.values(), default=0)
    latest_finish, latest_start = {}, {}
    for node in reversed(order):
        finish = min([latest_start[s] for s in succs[node]], default=project_end)
        latest_finish[node] = finish
        latest_start[node] = finish - duration[node]

    return {n for n in by_name if latest_start[n] - earliest_start[n] == 0}


@frappe.whitelist(methods=["POST"])
def update_task_dates(task, exp_start_date=None, exp_end_date=None):
    """Called when a Gantt bar is dragged or resized."""
    _ensure_app_access()
    doc = frappe.get_doc("Task", task)
    # ERPNext v16 made exp_start_date/exp_end_date Datetime (they were Date in
    # v15). The SPA sends date-only strings, so anchor the start at the top of
    # the day and the end at the bottom: that keeps a same-day task from being
    # a zero-length bar and preserves inclusive-day semantics. Mixing a date
    # with the datetime already on the doc would also raise TypeError.
    if exp_start_date:
        doc.exp_start_date = _day_start(exp_start_date)
    if exp_end_date:
        doc.exp_end_date = _day_end(exp_end_date)
    if (
        doc.exp_start_date
        and doc.exp_end_date
        and get_datetime(doc.exp_end_date) < get_datetime(doc.exp_start_date)
    ):
        frappe.throw(_("End date cannot be before start date"))
    doc.save()
    return {
        "name": doc.name,
        "exp_start_date": doc.exp_start_date,
        "exp_end_date": doc.exp_end_date,
    }


@frappe.whitelist(methods=["POST"])
def set_task_dependency(task, depends_on):
    """Draw a dependency link. Stock ERPNext's Gantt is read-only for links."""
    _ensure_app_access()
    if task == depends_on:
        frappe.throw(_("A task cannot depend on itself"))
    if not frappe.db.exists("Task", depends_on):
        frappe.throw(_("Task {0} not found").format(depends_on))
    # don't let a user link to (and thereby read the details of) a task they
    # have no read access to
    frappe.has_permission("Task", doc=depends_on, throw=True)

    doc = frappe.get_doc("Task", task)
    if any(row.task == depends_on for row in doc.depends_on or []):
        return get_task_dependencies(task)

    doc.append("depends_on", {"task": depends_on})
    # ERPNext's check_recursion raises CircularReferenceError on a cycle
    doc.save()
    return get_task_dependencies(task)


@frappe.whitelist(methods=["POST"])
def remove_task_dependency(task, depends_on):
    _ensure_app_access()
    doc = frappe.get_doc("Task", task)
    rows = [row for row in doc.depends_on or [] if row.task != depends_on]
    if len(rows) == len(doc.depends_on or []):
        frappe.throw(_("Task {0} is not a dependency of {1}").format(depends_on, task))
    doc.set("depends_on", rows)
    doc.save()
    return get_task_dependencies(task)


@frappe.whitelist()
def get_task_dependencies(task):
    _ensure_app_access()
    frappe.has_permission("Task", doc=task, throw=True)
    rows = frappe.get_all(
        "Task Depends On",
        filters={"parenttype": "Task", "parent": task},
        fields=["task"],
    )
    out = []
    for row in rows:
        if not row.task:
            continue
        if not frappe.has_permission("Task", doc=row.task):
            # the link exists but its details are not this user's to see
            out.append({"name": row.task, "subject": _("(no access)"), "status": None})
            continue
        info = frappe.db.get_value(
            "Task", row.task, ["name", "subject", "status"], as_dict=True
        )
        if info:
            out.append(info)
    return out


# ---------------------------------------------------------------------------
# Board ordering
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def reorder_column(project, status, task_names):
    """Persist card order within a column.

    Order only — a cross-column move must go through `update_task_status` so
    the dependency gate runs. Written with db.set_value because reordering is
    high-frequency and must not bump `modified` or re-run validation.
    """
    _ensure_app_access()
    task_names = frappe.parse_json(task_names) or []
    if status not in AGILE_STATUSES:
        frappe.throw(_("Invalid status: {0}").format(status))
    if not task_names:
        return {"ordered": 0}

    # This is a write, so require write access — not just read on the project.
    frappe.has_permission("Project", ptype="read", doc=project, throw=True)

    # get_list applies the user's own permissions, so tasks they cannot see
    # never enter the set; then check write on each before touching it.
    visible = set(
        frappe.get_list(
            "Task",
            filters={"project": project, "name": ["in", task_names]},
            pluck="name",
            limit_page_length=0,
        )
    )
    ordered = 0
    for index, name in enumerate(task_names):
        if name in visible and frappe.has_permission("Task", ptype="write", doc=name):
            frappe.db.set_value("Task", name, "board_order", index, update_modified=False)
            ordered += 1
    return {"ordered": ordered}


# ---------------------------------------------------------------------------
# My Work (cross-project)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_my_work():
    """Everything assigned to the current user across every project."""
    _ensure_app_access()
    user = frappe.session.user
    employee = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")

    # _assign is a JSON array string like ["a@b.com"]; quoting the needle stops
    # "a@b.com" from matching "aa@b.com"
    or_filters = [["Task", "_assign", "like", f'%"{user}"%']]
    if employee:
        or_filters.append(["Task", "sme_responsible", "=", employee])

    tasks = frappe.get_list(
        "Task",
        filters={"is_template": 0, "is_group": 0, "status": ["!=", DONE]},
        or_filters=or_filters,
        fields=LIST_FIELDS,
        order_by="exp_end_date asc",
        limit_page_length=0,
    )
    _decorate(tasks)

    project_names = {t.project for t in tasks if t.project}
    project_titles = {}
    if project_names:
        project_titles = {
            p.name: p.project_name
            for p in frappe.get_all(
                "Project",
                filters={"name": ["in", list(project_names)]},
                fields=["name", "project_name"],
            )
        }

    today = getdate(nowdate())
    week_end = add_days(today, 7)
    buckets = {"overdue": [], "today": [], "this_week": [], "later": [], "blocked": []}

    for task in tasks:
        task["project_name"] = project_titles.get(task.project)
        due = getdate(task.exp_end_date) if task.exp_end_date else None
        if task.get("is_blocked") or task.status == "Blocked":
            bucket = "blocked"
        elif due and due < today:
            bucket = "overdue"
        elif due and due == today:
            bucket = "today"
        elif due and due <= week_end:
            bucket = "this_week"
        else:
            bucket = "later"
        task["bucket"] = bucket
        buckets[bucket].append(task)

    return {
        "buckets": buckets,
        "counts": {key: len(value) for key, value in buckets.items()},
        "total": len(tasks),
        "employee": employee,
    }


# ---------------------------------------------------------------------------
# Saved views
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_views(project=None):
    _ensure_app_access()
    filters = {"user": frappe.session.user}
    views = frappe.get_all(
        "Agile Saved View",
        filters=filters,
        fields=[
            "name",
            "view_name",
            "project",
            "view_type",
            "is_default",
            "filters",
            "columns",
            "sort_field",
            "sort_order",
            "group_by",
        ],
        order_by="view_name asc",
        limit_page_length=0,
    )
    if project:
        views = [v for v in views if not v.project or v.project == project]
    for view in views:
        view["filters"] = frappe.parse_json(view.filters) if view.filters else {}
        view["columns"] = frappe.parse_json(view.columns) if view.columns else []
    return views


@frappe.whitelist(methods=["POST"])
def save_view(
    view_name,
    view_type,
    project=None,
    filters=None,
    columns=None,
    sort_field=None,
    sort_order="desc",
    group_by=None,
    is_default=0,
    name=None,
):
    _ensure_app_access()
    if view_type not in VIEW_TYPES:
        frappe.throw(_("Invalid view type: {0}").format(view_type))

    values = {
        "view_name": view_name,
        "view_type": view_type,
        "project": project,
        "filters": frappe.as_json(frappe.parse_json(filters) if filters else {}),
        "columns": frappe.as_json(frappe.parse_json(columns) if columns else []),
        "sort_field": sort_field,
        "sort_order": sort_order if sort_order in ("asc", "desc") else "desc",
        "group_by": group_by,
        "is_default": cint(is_default),
    }

    if name:
        doc = frappe.get_doc("Agile Saved View", name)
        if doc.user != frappe.session.user:
            frappe.throw(_("You can only edit your own saved views"), frappe.PermissionError)
        doc.update(values)
        doc.save()
    else:
        doc = frappe.get_doc(
            dict(doctype="Agile Saved View", user=frappe.session.user, **values)
        ).insert()
    return {"name": doc.name, "view_name": doc.view_name}


@frappe.whitelist(methods=["POST"])
def delete_view(name):
    _ensure_app_access()
    doc = frappe.get_doc("Agile Saved View", name)
    if doc.user != frappe.session.user:
        frappe.throw(_("You can only delete your own saved views"), frappe.PermissionError)
    doc.delete()
    return {"deleted": name}
