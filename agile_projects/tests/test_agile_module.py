"""Gate rules that need a document: the previous gate, and linked tasks.

Requires a bench (`bench --site <site> run-tests --app agile_projects`); the
rules themselves are in the Agile Module controller, so what is asserted here
is exactly what Desk enforces.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from agile_projects.agile_projects.doctype.agile_module.agile_module import (
    GATES,
    GateTransitionError,
)


class TestAgileModuleGates(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = frappe.get_doc(
            {"doctype": "Project", "project_name": "Gate Rule Fixture"}
        ).insert(ignore_permissions=True)

    def make_module(self, **kwargs):
        values = {
            "doctype": "Agile Module",
            "project": self.project.name,
            "module_name": kwargs.pop("module_name", "Inventory"),
            "system_platform": "ERPNext",
            "gate": "Configure",
        }
        values.update(kwargs)
        return frappe.get_doc(values).insert(ignore_permissions=True)

    def move(self, module, gate):
        module.reload()
        module.gate = gate
        module.save(ignore_permissions=True)
        return module

    # -- UAT ----------------------------------------------------------------

    def test_uat_refused_until_the_data_migration_is_done(self):
        module = self.make_module(module_name="Accounting", gate="Migrate")
        with self.assertRaises(GateTransitionError):
            self.move(module, "UAT")

        module.reload()
        module.data_migration_status = "Validated"
        module.save(ignore_permissions=True)
        self.move(module, "UAT")
        self.assertEqual(frappe.db.get_value("Agile Module", module.name, "gate"), "UAT")

    # -- Sign-off -----------------------------------------------------------

    def test_signoff_refused_while_a_linked_task_is_open(self):
        module = self.make_module(
            module_name="CRM", gate="UAT", data_migration_status="Validated"
        )
        task = frappe.get_doc(
            {
                "doctype": "Task",
                "subject": "Unfinished work",
                "project": self.project.name,
                "status": "To Do",
                "agile_module": module.name,
            }
        ).insert(ignore_permissions=True)

        with self.assertRaises(GateTransitionError):
            self.move(module, "Sign-off")

        task.status = "Done"
        task.save(ignore_permissions=True)
        self.move(module, "Sign-off")
        self.assertEqual(frappe.db.get_value("Agile Module", module.name, "gate"), "Sign-off")

    # -- Live ---------------------------------------------------------------

    def test_live_refused_without_functional_signoff(self):
        module = self.make_module(
            module_name="Selling", gate="Sign-off", data_migration_status="Validated"
        )
        with self.assertRaises(GateTransitionError):
            self.move(module, "Live")

        module.reload()
        module.functional_signoff = 1
        module.save(ignore_permissions=True)
        self.move(module, "Live")
        self.assertEqual(frappe.db.get_value("Agile Module", module.name, "gate"), "Live")

    # -- direction ----------------------------------------------------------

    def test_moving_backwards_is_always_allowed(self):
        module = self.make_module(
            module_name="Buying",
            gate="Sign-off",
            data_migration_status="Validated",
            functional_signoff=1,
        )
        self.move(module, "Configure")
        self.assertEqual(frappe.db.get_value("Agile Module", module.name, "gate"), "Configure")

    def test_a_jump_must_satisfy_every_gate_it_passes(self):
        """Configure -> Live in one drag is not a shortcut past UAT."""
        module = self.make_module(module_name="Assets", functional_signoff=1)
        with self.assertRaises(GateTransitionError):
            self.move(module, "Live")

    # -- uniqueness ---------------------------------------------------------

    def test_one_module_per_name_per_project(self):
        self.make_module(module_name="Support")
        with self.assertRaises(frappe.ValidationError):
            self.make_module(module_name="Support")

    def test_gate_options_match_the_controller(self):
        options = frappe.get_meta("Agile Module").get_field("gate").options.split("\n")
        self.assertEqual(options, GATES)
