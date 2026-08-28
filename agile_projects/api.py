"""Whitelisted API surface for the Agile Projects SPA (served at /agile).

Every endpoint goes through standard document permissions (`frappe.get_doc`
+ save/insert, or `frappe.get_list`) — nothing here bypasses roles. Reads of
child rows and low-sensitivity lookup lists (employees, activity types) use
`frappe.get_all` but are gated behind `check_app_permission`.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Count, Sum
from frappe.utils import add_to_date, flt, get_datetime, now_datetime

from agile_projects.overrides.task import AGILE_STATUSES, DONE


def _sum_logged_hours(task):
    """Total submitted hours for a task. Uses the query builder because recent
    Frappe rejects SQL functions passed as strings in a `fields` list."""
    tsd = frappe.qb.DocType("Timesheet Detail")
    result = (
        frappe.qb.from_(tsd)
        .select(Sum(tsd.hours).as_("total_hours"))
        .where((tsd.task == task) & (tsd.docstatus == 1))
        .run(as_dict=True)
    )
    return flt(result[0].total_hours) if result and result[0].total_hours else 0

ALLOWED_ROLES = {"System Manager", "Projects Manager", "Projects User"}

TASK_EDITABLE_FIELDS = {
    "subject",
    "description",
    "priority",
    "complexity_points",
    "sme_responsible",
    "exp_start_date",
    "exp_end_date",
    "expected_time",
    "progress",
}

CHECKLIST_EDITABLE_FIELDS = {
    "module_name",
    "system_platform",
    "configuration_status",
    "data_migration_status",
    "functional_signoff",
}


@frappe.whitelist()
def check_app_permission():
    """Used by add_to_apps_screen, the /agile www page and every endpoint here."""
    if frappe.session.user == "Administrator":
        return True
    return bool(ALLOWED_ROLES & set(frappe.get_roles()))


def _ensure_app_access():
    if not check_app_permission():
        frappe.throw(
            _("You do not have permission to access Agile Projects"),
            frappe.PermissionError,
        )


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_projects():
    _ensure_app_access()
    projects = frappe.get_list(
        "Project",
        fields=[
            "name",
            "project_name",
            "status",
            "priority",
            "percent_complete",
            "expected_start_date",
            "expected_end_date",
            "company",
        ],
        order_by="modified desc",
        limit_page_length=0,
    )
    if not projects:
        return []

    names = [p.name for p in projects]
    # Recent Frappe blocks SQL functions passed as strings in `fields`; use the
    # query builder for the grouped count instead.
    task_table = frappe.qb.DocType("Task")
    task_counts = (
        frappe.qb.from_(task_table)
        .select(
            task_table.project,
            task_table.status,
            Count(task_table.name).as_("count"),
        )
        .where(
            task_table.project.isin(names)
            & (task_table.is_group == 0)
            & (task_table.is_template == 0)
        )
        .groupby(task_table.project, task_table.status)
        .run(as_dict=True)
    )
    checklist_rows = frappe.get_all(
        "ERP Module Readiness Checklist",
        filters={"parenttype": "Project", "parent": ["in", names]},
        fields=["parent", "functional_signoff"],
    )

    tasks_by_project = {}
    for row in task_counts:
        stats = tasks_by_project.setdefault(row.project, {"total": 0, "done": 0})
        stats["total"] += row.count
        if row.status == DONE:
            stats["done"] += row.count

    checklist_by_project = {}
    for row in checklist_rows:
        stats = checklist_by_project.setdefault(row.parent, {"total": 0, "signed_off": 0})
        stats["total"] += 1
        if row.functional_signoff:
            stats["signed_off"] += 1

    for p in projects:
        tstats = tasks_by_project.get(p.name, {})
        cstats = checklist_by_project.get(p.name, {})
        p.update(
            {
                "total_tasks": tstats.get("total", 0),
                "done_tasks": tstats.get("done", 0),
                "checklist_total": cstats.get("total", 0),
                "checklist_signed_off": cstats.get("signed_off", 0),
            }
        )
    return projects


# ---------------------------------------------------------------------------
# Kanban board
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_board(project):
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

    # Group tasks are tree containers, not workable cards; the progress
    # calculation excludes them too, so counts and percent stay consistent.
    tasks = frappe.get_list(
        "Task",
        filters={"project": project, "is_group": 0, "is_template": 0},
        fields=[
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
        ],
        order_by="modified desc",
        limit_page_length=0,
    )

    blockers = _get_blockers([t.name for t in tasks])
    _attach_employee_info(tasks)

    columns = {status: [] for status in AGILE_STATUSES}
    for task in tasks:
        task["blocked_by"] = blockers.get(task.name, [])
        task["is_blocked"] = task.status != DONE and any(
            dep["status"] != DONE for dep in task["blocked_by"]
        )
        status = task.status if task.status in columns else "Backlog"
        columns[status].append(task)

    return {
        "project": meta,
        "statuses": AGILE_STATUSES,
        "columns": [{"status": s, "tasks": columns[s]} for s in AGILE_STATUSES],
    }


def _get_blockers(task_names):
    """One batched pass over the standard Task Depends On child table."""
    if not task_names:
        return {}
    dep_rows = frappe.get_all(
        "Task Depends On",
        filters={"parenttype": "Task", "parent": ["in", task_names]},
        fields=["parent", "task"],
    )
    dep_task_names = {row.task for row in dep_rows if row.task}
    dep_info = {}
    if dep_task_names:
        for t in frappe.get_all(
            "Task",
            filters={"name": ["in", list(dep_task_names)]},
            fields=["name", "subject", "status"],
        ):
            dep_info[t.name] = t

    blockers = {}
    for row in dep_rows:
        info = dep_info.get(row.task)
        if info:
            blockers.setdefault(row.parent, []).append(
                {"task": info.name, "subject": info.subject, "status": info.status}
            )
    return blockers


def _attach_employee_info(tasks):
    employee_names = {t.sme_responsible for t in tasks if t.get("sme_responsible")}
    if not employee_names:
        return
    employees = {
        e.name: e
        for e in frappe.get_all(
            "Employee",
            filters={"name": ["in", list(employee_names)]},
            fields=["name", "employee_name", "image"],
        )
    }
    for t in tasks:
        emp = employees.get(t.get("sme_responsible"))
        t["sme_name"] = emp.employee_name if emp else None
        t["sme_image"] = emp.image if emp else None


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def update_task_status(task, status):
    """Server-enforced transition: AgileTask.validate_status throws
    AgileDependencyError if a dependency is not Done."""
    _ensure_app_access()
    if status not in AGILE_STATUSES:
        frappe.throw(_("Invalid status: {0}").format(status))
    doc = frappe.get_doc("Task", task)
    doc.status = status
    doc.save()
    return {
        "name": doc.name,
        "status": doc.status,
        "progress": doc.progress,
        "completed_on": doc.completed_on,
        "percent_complete": frappe.db.get_value("Project", doc.project, "percent_complete")
        if doc.project
        else None,
    }


@frappe.whitelist()
def get_task(task):
    _ensure_app_access()
    doc = frappe.get_doc("Task", task)
    doc.check_permission("read")

    depends_on = []
    for row in doc.depends_on or []:
        if not row.task:
            continue
        info = frappe.db.get_value("Task", row.task, ["name", "subject", "status"], as_dict=True)
        if info:
            depends_on.append(info)

    total_hours = _sum_logged_hours(doc.name)

    out = {
        field: doc.get(field)
        for field in (
            "name",
            "subject",
            "description",
            "status",
            "priority",
            "project",
            "complexity_points",
            "sme_responsible",
            "exp_start_date",
            "exp_end_date",
            "expected_time",
            "progress",
            "actual_time",
            "completed_on",
            "completed_by",
            "owner",
        )
    }
    out.update(
        {
            "project_name": frappe.db.get_value("Project", doc.project, "project_name")
            if doc.project
            else None,
            "sme_name": frappe.db.get_value("Employee", doc.sme_responsible, "employee_name")
            if doc.get("sme_responsible")
            else None,
            "depends_on": depends_on,
            "is_blocked": doc.status != DONE
            and any(dep.status != DONE for dep in depends_on),
            "total_hours": total_hours,
        }
    )
    return out


@frappe.whitelist(methods=["POST"])
def create_task(
    project,
    subject,
    description=None,
    status="Backlog",
    priority=None,
    complexity_points=None,
    sme_responsible=None,
    exp_end_date=None,
):
    _ensure_app_access()
    if status not in AGILE_STATUSES:
        frappe.throw(_("Invalid status: {0}").format(status))
    doc = frappe.get_doc(
        {
            "doctype": "Task",
            "project": project,
            "subject": subject,
            "description": description,
            "status": status,
            "priority": priority,
            "complexity_points": complexity_points,
            "sme_responsible": sme_responsible,
            "exp_end_date": exp_end_date,
        }
    ).insert()
    return get_task(doc.name)


@frappe.whitelist(methods=["POST"])
def update_task(task, fields):
    _ensure_app_access()
    fields = frappe.parse_json(fields) or {}
    invalid = set(fields) - TASK_EDITABLE_FIELDS
    if invalid:
        frappe.throw(
            _("Field(s) {0} cannot be updated from the board").format(", ".join(sorted(invalid)))
        )
    doc = frappe.get_doc("Task", task)
    doc.update(fields)
    doc.save()
    return get_task(doc.name)


# ---------------------------------------------------------------------------
# ERP Module Readiness Checklist (child rows on Project)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_checklist(project):
    _ensure_app_access()
    frappe.has_permission("Project", doc=project, throw=True)
    rows = frappe.get_all(
        "ERP Module Readiness Checklist",
        filters={"parenttype": "Project", "parent": project},
        fields=[
            "name",
            "idx",
            "module_name",
            "system_platform",
            "configuration_status",
            "data_migration_status",
            "functional_signoff",
        ],
        order_by="idx asc",
    )
    return {
        "rows": rows,
        "percent_complete": frappe.db.get_value("Project", project, "percent_complete"),
    }


def _checklist_row_dict(row):
    return {
        "name": row.name,
        "idx": row.idx,
        "module_name": row.module_name,
        "system_platform": row.system_platform,
        "configuration_status": row.configuration_status,
        "data_migration_status": row.data_migration_status,
        "functional_signoff": row.functional_signoff,
    }


@frappe.whitelist(methods=["POST"])
def add_checklist_row(
    project, module_name, system_platform, configuration_status=None, data_migration_status=None
):
    _ensure_app_access()
    doc = frappe.get_doc("Project", project)
    row = doc.append(
        "erp_module_readiness",
        {
            "module_name": module_name,
            "system_platform": system_platform,
            "configuration_status": configuration_status or "Not Started",
            "data_migration_status": data_migration_status or "Not Started",
        },
    )
    doc.save()
    return {"row": _checklist_row_dict(row), "percent_complete": doc.percent_complete}


@frappe.whitelist(methods=["POST"])
def update_checklist_row(project, row_name, fields):
    _ensure_app_access()
    fields = frappe.parse_json(fields) or {}
    invalid = set(fields) - CHECKLIST_EDITABLE_FIELDS
    if invalid:
        frappe.throw(
            _("Field(s) {0} cannot be updated on the checklist").format(", ".join(sorted(invalid)))
        )
    doc = frappe.get_doc("Project", project)
    row = next((r for r in doc.get("erp_module_readiness") or [] if r.name == row_name), None)
    if not row:
        frappe.throw(_("Checklist row {0} not found in project {1}").format(row_name, project))
    row.update(fields)
    doc.save()
    return {"row": _checklist_row_dict(row), "percent_complete": doc.percent_complete}


@frappe.whitelist(methods=["POST"])
def delete_checklist_row(project, row_name):
    _ensure_app_access()
    doc = frappe.get_doc("Project", project)
    rows = [r for r in doc.get("erp_module_readiness") or [] if r.name != row_name]
    if len(rows) == len(doc.get("erp_module_readiness") or []):
        frappe.throw(_("Checklist row {0} not found in project {1}").format(row_name, project))
    doc.set("erp_module_readiness", rows)
    doc.save()
    return {"percent_complete": doc.percent_complete}


# ---------------------------------------------------------------------------
# Timesheets
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def log_time(task, hours, activity_type, description=None, from_time=None):
    """Create and submit a standard ERPNext Timesheet with one time log row.

    Submission matters: task.actual_time and project costing only aggregate
    submitted timesheets.
    """
    _ensure_app_access()
    task_doc = frappe.get_doc("Task", task)
    task_doc.check_permission("read")

    hours = flt(hours)
    if hours <= 0:
        frappe.throw(_("Hours must be greater than zero"))

    employee = frappe.db.get_value(
        "Employee",
        {"user_id": frappe.session.user, "status": "Active"},
        ["name", "company"],
        as_dict=True,
    )
    if not employee:
        frappe.throw(
            _(
                "No active Employee record is linked to user {0}, so time cannot be logged. "
                "Ask HR to set 'User ID' on your Employee record."
            ).format(frappe.session.user)
        )

    if from_time:
        # Use a window the user chose verbatim.
        from_time = get_datetime(from_time)
        to_time = add_to_date(from_time, hours=hours, as_datetime=True)
    else:
        # Anchor the end at now and backdate the start: projecting the hours
        # into the future would make every back-to-back log collide with
        # ERPNext's employee overlap validation.
        to_time = now_datetime()
        from_time = add_to_date(to_time, hours=-hours, as_datetime=True)
        latest_end = frappe.db.sql(
            """
            select max(tsd.to_time)
            from `tabTimesheet Detail` tsd
            join `tabTimesheet` ts on tsd.parent = ts.name
            where ts.employee = %s and ts.docstatus < 2 and tsd.to_time > %s
            """,
            (employee.name, from_time),
        )
        latest_end = latest_end[0][0] if latest_end and latest_end[0] else None
        if latest_end and get_datetime(latest_end) > from_time:
            # Shift the whole window past the last existing log, keeping its
            # length == hours (ERPNext recomputes hours from the window).
            from_time = get_datetime(latest_end)
            to_time = add_to_date(from_time, hours=hours, as_datetime=True)

    timesheet = frappe.get_doc(
        {
            "doctype": "Timesheet",
            "employee": employee.name,
            "company": employee.company or frappe.defaults.get_global_default("company"),
            "parent_project": task_doc.project,
            "time_logs": [
                {
                    "activity_type": activity_type,
                    "from_time": from_time,
                    "to_time": to_time,
                    "hours": hours,
                    "project": task_doc.project,
                    "task": task_doc.name,
                    "description": description,
                }
            ],
        }
    )
    from erpnext.projects.doctype.timesheet.timesheet import OverlapError

    try:
        timesheet.insert()
        timesheet.submit()
    except OverlapError:
        frappe.throw(
            _(
                "This window ({0} – {1}) overlaps one of your existing time logs. "
                "Pick an explicit start time and try again."
            ).format(from_time, to_time),
            OverlapError,
        )

    return {
        "timesheet": timesheet.name,
        "hours": hours,
        "from_time": str(from_time),
        "to_time": str(to_time),
    }


@frappe.whitelist()
def get_task_timesheets(task):
    _ensure_app_access()
    frappe.has_permission("Task", doc=task, throw=True)
    logs = frappe.get_all(
        "Timesheet Detail",
        filters={"task": task, "docstatus": 1},
        fields=["name", "parent", "activity_type", "from_time", "to_time", "hours", "description"],
        order_by="from_time desc",
        limit_page_length=50,
    )
    if logs:
        parents = list({row.parent for row in logs})
        timesheets = {
            ts.name: ts
            for ts in frappe.get_all(
                "Timesheet",
                filters={"name": ["in", parents]},
                fields=["name", "employee", "employee_name"],
            )
        }
        for row in logs:
            ts = timesheets.get(row.parent)
            row["employee"] = ts.employee if ts else None
            row["employee_name"] = ts.employee_name if ts else None

    return {"logs": logs, "total_hours": _sum_logged_hours(task)}


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_employees(txt=""):
    _ensure_app_access()
    or_filters = None
    if txt:
        or_filters = [
            ["Employee", "employee_name", "like", f"%{txt}%"],
            ["Employee", "name", "like", f"%{txt}%"],
        ]
    return frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        or_filters=or_filters,
        fields=["name", "employee_name", "designation", "user_id", "image"],
        order_by="employee_name asc",
        # the picker filters client-side over this list; cap defensively
        limit_page_length=1000,
    )


@frappe.whitelist()
def get_activity_types():
    _ensure_app_access()
    return frappe.get_all("Activity Type", pluck="name", order_by="name asc")


@frappe.whitelist()
def get_user_info():
    _ensure_app_access()
    user = frappe.session.user
    info = frappe.db.get_value("User", user, ["full_name", "user_image"], as_dict=True) or {}
    employee = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
    return {
        "user": user,
        "full_name": info.get("full_name"),
        "user_image": info.get("user_image"),
        "employee": employee,
        "can_log_time": bool(employee),
    }
