"""Schema extensions applied to standard ERPNext doctypes.

Runs on `after_install` and is re-asserted on every `after_migrate` so an
ERPNext/Frappe migration can never strand our custom fields or property
setters. Everything here is idempotent.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.utils import cint

AGILE_STATUSES = ["Backlog", "To Do", "In Progress", "QA/Code Review", "Blocked", "Done"]
AGILE_STATUS_OPTIONS = "\n".join(AGILE_STATUSES)

# ERPNext's standard Task statuses, mapped onto the agile workflow. Used both
# for the one-time data migration on install and by AgileTask.normalize_status
# to self-heal documents written by core code paths that hard-code literals.
LEGACY_STATUS_MAP = {
    "Open": "To Do",
    "Working": "In Progress",
    "Pending Review": "QA/Code Review",
    "Overdue": "To Do",
    "Template": "Backlog",
    "Completed": "Done",
    "Cancelled": "Done",
}

CUSTOM_FIELDS = {
    "Task": [
        {
            "fieldname": "complexity_points",
            "label": "Complexity Points",
            "fieldtype": "Select",
            "options": "\n1\n2\n3\n5\n8\n13",
            "insert_after": "priority",
            "in_list_view": 1,
            "in_standard_filter": 1,
        },
        {
            "fieldname": "sme_responsible",
            "label": "SME Responsible",
            "fieldtype": "Link",
            "options": "Employee",
            "insert_after": "complexity_points",
            "in_standard_filter": 1,
            "description": "Subject-matter expert accountable for this task (distinct from the document owner)",
        },
        {
            "fieldname": "blocked_reason",
            "label": "Blocked Reason",
            "fieldtype": "Small Text",
            "insert_after": "sme_responsible",
            "depends_on": 'eval: doc.status == "Blocked"',
        },
        {
            # Real indexed ordering column. Frappe's stock Kanban keeps card
            # order as a JSON blob on Kanban Board Column, which cannot be
            # sorted or reported on; this can.
            "fieldname": "board_order",
            "label": "Board Order",
            "fieldtype": "Int",
            "insert_after": "blocked_reason",
            "default": "0",
            "hidden": 1,
            "no_copy": 1,
            "search_index": 1,
        },
        {
            # Rolls a task up to the module whose gate it gates. Link options
            # name a doctype this app defines, which is why this lives in
            # ensure_customizations() — Frappe syncs the app's doctypes before
            # both after_install and after_migrate, so the target always exists.
            "fieldname": "agile_module",
            "label": "Module",
            "fieldtype": "Link",
            "options": "Agile Module",
            "insert_after": "board_order",
            "in_standard_filter": 1,
            "search_index": 1,
        },
    ],
    "Project": [
        {
            "fieldname": "erp_readiness_section",
            "label": "ERP Module Readiness",
            "fieldtype": "Section Break",
            "insert_after": "customer",
            "collapsible": 1,
        },
        {
            "fieldname": "erp_module_readiness",
            "label": "ERP Module Readiness Checklist",
            "fieldtype": "Table",
            "options": "ERP Module Readiness Checklist",
            "insert_after": "erp_readiness_section",
        },
    ],
}

PROPERTY_SETTERS = [
    # (doctype, fieldname, property, value, property_type[, for_doctype])
    ("Task", "status", "options", AGILE_STATUS_OPTIONS, "Text"),
    ("Task", "status", "default", "Backlog", "Text"),
    ("Task", "completed_by", "depends_on", 'eval: doc.status == "Done"', "Text"),
    ("Task", "completed_on", "depends_on", 'eval: doc.status == "Done"', "Text"),
    # AgileTask.set_completion_fields fills completed_on itself
    ("Task", "completed_on", "mandatory_depends_on", "", "Text"),
    # Superseded by the Agile Module doctype. Kept visible but frozen for one
    # release as the rollback path for the checklist -> modules migration;
    # removing this line is all it takes to thaw it.
    ("Project", "erp_module_readiness", "read_only", "1", "Check"),
    # Task does not version its own changes by default, so the activity
    # timeline would have nothing to read. for_doctype=True makes this a
    # DocType-level property rather than a DocField one.
    ("Task", None, "track_changes", "1", "Check", True),
]


def after_install():
    ensure_customizations()
    migrate_legacy_task_statuses()
    migrate_checklist_to_modules()
    recompute_all_project_progress()


def after_migrate():
    ensure_customizations()


def ensure_customizations():
    create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
    for setter in PROPERTY_SETTERS:
        doctype, fieldname, prop, value, property_type = setter[:5]
        for_doctype = setter[5] if len(setter) > 5 else False
        make_property_setter(
            doctype,
            fieldname,
            prop,
            value,
            property_type,
            for_doctype=for_doctype,
            validate_fields_for_doctype=False,
        )
    frappe.clear_cache(doctype="Task")
    frappe.clear_cache(doctype="Project")


def migrate_legacy_task_statuses():
    for old, new in LEGACY_STATUS_MAP.items():
        frappe.db.set_value("Task", {"status": old}, "status", new, update_modified=False)


def recompute_all_project_progress():
    from agile_projects.progress import update_project_progress

    for project in frappe.get_all("Project", pluck="name"):
        update_project_progress(project)


# ---------------------------------------------------------------------------
# ERP Module Readiness Checklist -> Agile Module
# ---------------------------------------------------------------------------

# Conservative ladder: derive the furthest gate the old row can actually
# evidence. Deliberately never derives "Live" — going live is a human
# assertion, and a checkbox from the previous data model cannot prove it.
CONFIG_DONE = ("Configured", "Verified")
MIGRATION_DONE = ("Migrated", "Validated")


def derive_gate(row):
    """Pure function so it can be unit-tested without a bench."""
    if cint(row.get("functional_signoff")):
        return "Sign-off"
    if row.get("data_migration_status") in MIGRATION_DONE:
        return "UAT"
    if row.get("configuration_status") in CONFIG_DONE:
        return "Migrate"
    return "Configure"


def migrate_checklist_to_modules():
    """Create one Agile Module per legacy checklist row.

    Idempotent by (project, module_name): a re-run creates nothing, so it is
    safe on every migrate. Additive — no existing row is modified or deleted,
    which is what makes the frozen legacy grid a real rollback path.
    """
    if not frappe.db.exists("DocType", "ERP Module Readiness Checklist"):
        return 0

    rows = frappe.get_all(
        "ERP Module Readiness Checklist",
        filters={"parenttype": "Project"},
        fields=[
            "parent",
            "module_name",
            "system_platform",
            "configuration_status",
            "data_migration_status",
            "functional_signoff",
        ],
        order_by="parent asc, idx asc",
    )
    if not rows:
        return 0

    existing = {
        (m.project, m.module_name)
        for m in frappe.get_all("Agile Module", fields=["project", "module_name"])
    }
    live_projects = set(frappe.get_all("Project", pluck="name"))

    created = 0
    for row in rows:
        key = (row.parent, row.module_name)
        # A checklist row can outlive its project (child rows are not always
        # cleaned up), and a duplicate module_name on one project collapses to
        # a single Agile Module — the first one wins.
        if key in existing or row.parent not in live_projects or not row.module_name:
            continue

        doc = frappe.get_doc(
            {
                "doctype": "Agile Module",
                "project": row.parent,
                "module_name": row.module_name,
                "system_platform": row.system_platform or "ERPNext",
                "gate": derive_gate(row),
                "configuration_status": row.configuration_status or "Not Started",
                "data_migration_status": row.data_migration_status or "Not Started",
                "functional_signoff": cint(row.functional_signoff),
            }
        )
        # The gate is derived from the row's own data, so the forward-transition
        # rules would be checking the migration against itself.
        doc.flags.ignore_gate_validation = True
        doc.insert(ignore_permissions=True)
        existing.add(key)
        created += 1

    return created
