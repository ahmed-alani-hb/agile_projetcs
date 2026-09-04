"""One step of the go-live runbook.

Cutover is the riskiest hour of an ERP rollout and the one nobody wants to
improvise. A step records who owns it, when it was meant to run, when it
actually ran, and what has to be finished before it can start.

`depends_on` is enforced on completion rather than on start, so a team can
begin preparing a step early — only declaring it done out of order is refused.
"""

import frappe
from frappe import _
from frappe.model.document import Document

STATUSES = ["Pending", "In Progress", "Done", "Skipped", "Failed"]

# A dependency is satisfied by either outcome: a skipped step was a conscious
# decision not to run it, which should not wedge the rest of the runbook.
SATISFIED = ("Done", "Skipped")


class CutoverDependencyError(frappe.ValidationError):
    pass


class CutoverStep(Document):
    def validate(self):
        self.validate_self_dependency()
        self.validate_dependency_done()

    def validate_self_dependency(self):
        if self.depends_on and self.depends_on == self.name:
            frappe.throw(
                _("A cutover step cannot depend on itself."),
                CutoverDependencyError,
            )

    def validate_dependency_done(self):
        if self.status not in SATISFIED or not self.depends_on:
            return
        previous = self.get_db_value("status") if not self.is_new() else None
        if self.status == previous:
            return

        blocker = frappe.db.get_value(
            "Cutover Step", self.depends_on, ["title", "status"], as_dict=True
        )
        if blocker and blocker.status not in SATISFIED:
            frappe.throw(
                _("Cannot complete {0}: it depends on {1}, which is {2}.").format(
                    frappe.bold(self.title),
                    frappe.bold(blocker.title),
                    frappe.bold(_(blocker.status)),
                ),
                CutoverDependencyError,
                title=_("Step Blocked"),
            )
