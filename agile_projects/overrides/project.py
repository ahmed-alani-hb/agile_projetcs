import frappe
from frappe import _
from frappe.utils import flt

from erpnext.projects.doctype.project.project import Project

from agile_projects.progress import compute_project_progress


class AgileProject(Project):
    def update_percent_complete(self):
        # Replaces Project.update_percent_complete. Core counts tasks with
        # status in ("Completed", "Cancelled") — statuses that never occur
        # under the agile workflow, so its percent is always 0 — and then
        # derives self.status from that stale percent, reverting "Completed"
        # projects to "Open" on every save and on every task update.
        # Structure below mirrors core (v15) with agile-aware values.
        if self.status == "Completed":
            if len(frappe.get_all("Task", dict(project=self.name))) == 0:
                # core semantics: a project without tasks can complete
                self.percent_complete_method = "Manual"
                self.percent_complete = 100

        if self.percent_complete_method == "Manual":
            if self.status == "Completed":
                self.percent_complete = 100
            elif flt(self.percent_complete) < 0 or flt(self.percent_complete) > 100:
                frappe.throw(_("% Complete must be between 0 and 100"))
            return

        self.percent_complete = compute_project_progress(
            self.name, checklist_rows=self.get("erp_module_readiness") or []
        )

        # don't update status if it is manually set to cancelled or on hold
        if self.status in ("Cancelled", "On hold"):
            return

        if not self.has_progress_content():
            # nothing to derive a status from — keep whatever the user set
            return

        self.status = "Completed" if flt(self.percent_complete) == 100 else "Open"

    def has_progress_content(self):
        if self.get("erp_module_readiness"):
            return True
        if frappe.db.exists("Agile Module", {"project": self.name}):
            return True
        return bool(
            frappe.db.exists("Task", {"project": self.name, "is_group": 0, "is_template": 0})
        )
