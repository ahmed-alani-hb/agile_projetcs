"""Project progress: complexity-point-weighted task completion blended with
ERP Module Readiness sign-offs.

ERPNext's own `Project.update_percent_complete` counts tasks with status in
("Completed", "Cancelled") — statuses that no longer exist under the agile
workflow — and then derives Project.status from that stale percent. The
AgileProject override (agile_projects/overrides/project.py) replaces that
calculation on every controller path; the Task doc-event handlers here are a
consistency backstop for direct writes (frappe.db.set_value paths) and keep
both percent_complete and the derived status in sync.
"""

import frappe
from frappe.utils import cint, flt

TASK_SHARE = 0.7
CHECKLIST_SHARE = 0.3
DONE = "Done"


def on_task_change(doc, method=None):
    """Task doc_event (on_update / after_delete). Also refreshes the previous
    project when a task is moved between projects."""
    projects = set()
    if doc.get("project"):
        projects.add(doc.project)
    before = doc.get_doc_before_save()
    if before and before.get("project") and before.project != doc.get("project"):
        projects.add(before.project)
    for project in projects:
        update_project_progress(project)


def update_project_progress(project):
    """Persist percent_complete (and the derived status, mirroring core's
    rules) directly — used from Task doc events, after core's own
    Project.update_project has already run."""
    meta = frappe.db.get_value(
        "Project", project, ["status", "percent_complete_method"], as_dict=True
    )
    if not meta:
        return
    if meta.percent_complete_method == "Manual":
        return

    task_pct, checklist_pct = get_progress_parts(project)
    percent = blend_progress(task_pct, checklist_pct)
    values = {"percent_complete": percent}
    has_content = not (task_pct is None and checklist_pct is None)
    if meta.status not in ("Cancelled", "On hold") and has_content:
        values["status"] = "Completed" if flt(percent) == 100 else "Open"
    frappe.db.set_value("Project", project, values, update_modified=False)


def compute_project_progress(project, checklist_rows=None):
    return blend_progress(*get_progress_parts(project, checklist_rows))


def get_progress_parts(project, checklist_rows=None):
    """Returns (task_pct, checklist_pct); each is None when there is nothing
    of that kind to measure."""
    tasks = frappe.get_all(
        "Task",
        filters={"project": project, "is_group": 0, "is_template": 0},
        fields=["status", "complexity_points"],
    )
    if checklist_rows is None:
        checklist_rows = frappe.get_all(
            "ERP Module Readiness Checklist",
            filters={"parenttype": "Project", "parent": project},
            fields=["functional_signoff"],
        )

    # Unestimated tasks count as 1 point so they still move the needle.
    total_points = sum(cint(t.complexity_points) or 1 for t in tasks)
    done_points = sum(cint(t.complexity_points) or 1 for t in tasks if t.status == DONE)
    task_pct = (done_points / total_points * 100) if total_points else None

    total_rows = len(checklist_rows)
    signed = sum(1 for row in checklist_rows if cint(row.get("functional_signoff")))
    checklist_pct = (signed / total_rows * 100) if total_rows else None

    return task_pct, checklist_pct


def blend_progress(task_pct, checklist_pct):
    if task_pct is None and checklist_pct is None:
        return 0
    if checklist_pct is None:
        return flt(task_pct, 2)
    if task_pct is None:
        return flt(checklist_pct, 2)
    return flt(TASK_SHARE * task_pct + CHECKLIST_SHARE * checklist_pct, 2)
