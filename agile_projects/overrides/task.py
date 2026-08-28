import frappe
from frappe import _
from frappe.desk.form.assign_to import close_all_assignments
from frappe.utils import flt, nowdate

from erpnext.projects.doctype.task.task import Task

AGILE_STATUSES = ["Backlog", "To Do", "In Progress", "QA/Code Review", "Blocked", "Done"]
DONE = "Done"

# ERPNext core still writes its own status literals from a few code paths
# (project templates insert "Open"; `set_project_status` db-sets "Completed" /
# "Cancelled" bypassing validation). validate() runs before Frappe's
# select-options check, so normalizing here lets those documents self-heal on
# their next save.
LEGACY_STATUS_MAP = {
    "Open": "To Do",
    "Working": "In Progress",
    "Pending Review": "QA/Code Review",
    "Overdue": "To Do",
    "Template": "Backlog",
    "Completed": "Done",
    "Cancelled": "Done",
}


class AgileDependencyError(frappe.ValidationError):
    pass


class AgileTask(Task):
    def validate(self):
        self.normalize_status()
        super().validate()
        self.set_completion_fields()

    def normalize_status(self):
        if not self.status:
            self.status = "Backlog"
        elif self.status in LEGACY_STATUS_MAP:
            self.status = LEGACY_STATUS_MAP[self.status]

    def validate_status(self):
        # Replaces Task.validate_status (is_template forcing + the "Completed"
        # dependency gate, both keyed on statuses that no longer exist).
        if self.status == self.get_db_value("status"):
            return
        if self.status in ("In Progress", DONE):
            self.validate_dependencies_done()

    def validate_dependencies_done(self):
        """Strict gate: a task cannot start (or finish) while any task it
        depends on is not Done."""
        unmet = []
        for row in self.depends_on or []:
            if not row.task:
                continue
            dep_status = frappe.db.get_value("Task", row.task, "status")
            if dep_status != DONE:
                unmet.append(_("{0} ({1})").format(frappe.bold(row.task), _(dep_status or "Unknown")))
        if unmet:
            frappe.throw(
                _("Cannot move task {0} to {1}: dependent tasks are not Done yet — {2}").format(
                    frappe.bold(self.name or self.subject),
                    frappe.bold(_(self.status)),
                    ", ".join(unmet),
                ),
                AgileDependencyError,
                title=_("Blocked by Dependencies"),
            )

    def validate_progress(self):
        # Replaces Task.validate_progress ("Completed" → 100).
        if flt(self.progress or 0) > 100:
            frappe.throw(_("Progress % for a task cannot be more than 100."))
        if self.status == DONE:
            self.progress = 100

    def set_completion_fields(self):
        if self.status == DONE:
            self.completed_on = self.completed_on or nowdate()
            self.completed_by = self.completed_by or frappe.session.user
        else:
            self.completed_on = None
            self.completed_by = None

    def unassign_todo(self):
        # Replaces Task.unassign_todo ("Completed" / "Cancelled").
        if self.status == DONE:
            close_all_assignments(self.doctype, self.name)

    def update_status(self):
        # Replaces Task.update_status: the daily `set_tasks_as_overdue`
        # scheduler would otherwise db_set the out-of-options "Overdue" status,
        # bypassing validation entirely.
        return
