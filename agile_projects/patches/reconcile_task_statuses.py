"""Re-map any Task left with a core ERPNext status literal.

ERPNext writes its own status literals from paths that bypass validation:
`Project.create_task_from_template` inserts "Open", `set_project_status`
db-sets "Completed"/"Cancelled", and — new in v16 —
`Timesheet.update_task_and_project` forces "Working"/"Completed" on every
submit. Documents self-heal on their next save via
AgileTask.normalize_status, but until then they sit with a status that is no
longer in the field's options. This runs on every migrate to reconcile them.
"""

import frappe

from agile_projects.overrides.task import LEGACY_STATUS_MAP


def execute():
    if not frappe.db.exists("DocType", "Task"):
        return
    for old, new in LEGACY_STATUS_MAP.items():
        frappe.db.set_value("Task", {"status": old}, "status", new, update_modified=False)
