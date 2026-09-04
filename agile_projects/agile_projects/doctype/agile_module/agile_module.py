"""An ERP module with a phase gate — the planning spine of a rollout.

Replaces the passive `ERP Module Readiness Checklist` child table, where
`configuration_status` and `data_migration_status` were stored but fed nothing
and a sign-off could be ticked with the data migration untouched.

The gate rules below are hard blocks raised from `validate`, so they hold in
Desk exactly as they do in the SPA — the same posture as the task dependency
gate in `agile_projects/overrides/task.py`.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

GATES = ["Configure", "Migrate", "UAT", "Sign-off", "Live"]

# How far through delivery each gate is. Feeds the readiness component of
# Project.percent_complete (see agile_projects/progress.py).
GATE_POSITION = {
    "Configure": 0.0,
    "Migrate": 0.25,
    "UAT": 0.5,
    "Sign-off": 0.75,
    "Live": 1.0,
}

MIGRATION_DONE = ("Migrated", "Validated")

DONE = "Done"

# How many blocking task IDs to name before falling back to "+N more".
MAX_NAMED_TASKS = 5


class GateTransitionError(frappe.ValidationError):
    pass


class DuplicateModuleError(frappe.ValidationError):
    pass


class AgileModule(Document):
    def validate(self):
        self.validate_unique()
        self.validate_gate_transition()

    def validate_unique(self):
        existing = frappe.db.exists(
            "Agile Module",
            {
                "project": self.project,
                "module_name": self.module_name,
                "name": ["!=", self.name or ""],
            },
        )
        if existing:
            frappe.throw(
                _("{0} already exists on project {1}.").format(
                    frappe.bold(self.module_name), frappe.bold(self.project)
                ),
                DuplicateModuleError,
                title=_("Duplicate Module"),
            )

    def validate_gate_transition(self):
        # Set by the checklist -> modules migration, whose gate is derived from
        # the row's own data — the rules would be checking it against itself.
        if self.flags.ignore_gate_validation:
            return
        previous = self.get_db_value("gate") if not self.is_new() else None
        if self.gate == previous:
            return
        if self.gate not in GATE_POSITION:
            frappe.throw(_("Unknown gate: {0}").format(self.gate), GateTransitionError)

        # Only forward moves are gated. Moving a module back is a correction and
        # is always allowed — refusing it would strand a mistake.
        if previous in GATE_POSITION and GATE_POSITION[self.gate] <= GATE_POSITION[previous]:
            return

        # Every gate the move passes through is checked, not just the one it
        # lands on. Otherwise dragging a card from Configure straight to Live
        # would satisfy only the sign-off rule and skip the migration and
        # open-task gates entirely.
        start = GATES.index(previous) + 1 if previous in GATE_POSITION else 0
        for gate in GATES[start : GATES.index(self.gate) + 1]:
            checker = self.CHECKERS.get(gate)
            if checker:
                checker(self)

    # -- individual gates ---------------------------------------------------

    def check_migrate(self):
        # Entering Migrate is not gated: configuration is often still being
        # tidied while migration scripts are written. Kept as an explicit
        # no-op so the gate table in the docstring stays honest.
        return

    def check_uat(self):
        if self.data_migration_status not in MIGRATION_DONE:
            self.refuse(
                "UAT",
                _("its data migration is {0}").format(
                    frappe.bold(_(self.data_migration_status or "Not Started"))
                ),
                _("Set Data Migration Status to Migrated or Validated first."),
            )

    def check_signoff(self):
        open_tasks = self.get_open_tasks()
        if open_tasks:
            named = ", ".join(
                "{0} ({1})".format(frappe.bold(t.name), _(t.status))
                for t in open_tasks[:MAX_NAMED_TASKS]
            )
            if len(open_tasks) > MAX_NAMED_TASKS:
                named += _(" +{0} more").format(len(open_tasks) - MAX_NAMED_TASKS)
            self.refuse(
                "Sign-off",
                _("{0} of its tasks are not Done — {1}").format(len(open_tasks), named),
                _("Finish or unlink those tasks first."),
            )

    def check_live(self):
        if not cint(self.functional_signoff):
            self.refuse(
                "Live",
                _("it has no functional sign-off"),
                _("Tick Functional Sign-off once the client has accepted the module."),
            )

    # -- helpers ------------------------------------------------------------

    def refuse(self, blocking_gate, because, remedy):
        """`blocking_gate` is the gate whose rule failed, which is not always
        the target: a jump from Configure to Live is refused at UAT first."""
        if blocking_gate == self.gate:
            headline = _("Cannot move {0} to {1}").format(
                frappe.bold(self.module_name), frappe.bold(_(self.gate))
            )
        else:
            headline = _("Cannot move {0} to {1} — it cannot pass {2}").format(
                frappe.bold(self.module_name),
                frappe.bold(_(self.gate)),
                frappe.bold(_(blocking_gate)),
            )
        frappe.throw(
            _("{0}: {1}. {2}").format(headline, because, remedy),
            GateTransitionError,
            title=_("Gate Blocked"),
        )

    CHECKERS = {
        "Migrate": check_migrate,
        "UAT": check_uat,
        "Sign-off": check_signoff,
        "Live": check_live,
    }

    def get_open_tasks(self):
        """Tasks linked to this module that are not Done.

        `get_all` bypasses permissions deliberately: the gate must consider
        every task, including ones the current user cannot see, or a module
        could be signed off by whoever has the narrowest view of it. Only the
        IDs and statuses of blockers are surfaced.
        """
        if self.is_new():
            return []
        return frappe.get_all(
            "Task",
            filters={
                "agile_module": self.name,
                "status": ["!=", DONE],
                "is_group": 0,
                "is_template": 0,
            },
            fields=["name", "status"],
            order_by="name asc",
        )
