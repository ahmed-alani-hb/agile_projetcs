"""Project progress: complexity-point-weighted task completion blended with
ERP Module Readiness sign-offs.

ERPNext's own `Project.update_percent_complete` counts tasks with status in
("Completed", "Cancelled") — statuses that no longer exist under the agile
workflow — so this app owns `Project.percent_complete`. Frappe runs doc-event
hooks after the controller method of the same name, so these handlers always
land after (and overwrite) core's value within the same transaction.
"""

import frappe
from frappe.utils import cint, flt

TASK_SHARE = 0.7
CHECKLIST_SHARE = 0.3
DONE = "Done"


def on_task_change(doc, method=None):
    """Task doc_event (on_update / after_delete)."""
    if doc.project:
        update_project_progress(doc.project)


def on_project_validate(doc, method=None):
    """Project doc_event (validate): recompute before every save so checklist
    edits made in Desk or via the SPA are reflected immediately."""
    doc.percent_complete = compute_project_progress(
        doc.name, checklist_rows=doc.get("erp_module_readiness") or []
    )


def update_project_progress(project):
    if not frappe.db.exists("Project", project):
        return
    percent = compute_project_progress(project)
    frappe.db.set_value("Project", project, "percent_complete", percent, update_modified=False)


def compute_project_progress(project, checklist_rows=None):
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

    if task_pct is None and checklist_pct is None:
        return 0
    if checklist_pct is None:
        return flt(task_pct, 2)
    if task_pct is None:
        return flt(checklist_pct, 2)
    return flt(TASK_SHARE * task_pct + CHECKLIST_SHARE * checklist_pct, 2)
