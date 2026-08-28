"""Schema extensions applied to standard ERPNext doctypes.

Runs on `after_install` and is re-asserted on every `after_migrate` so an
ERPNext/Frappe migration can never strand our custom fields or property
setters. Everything here is idempotent.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

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
    # (doctype, fieldname, property, value, property_type)
    ("Task", "status", "options", AGILE_STATUS_OPTIONS, "Text"),
    ("Task", "status", "default", "Backlog", "Text"),
    ("Task", "completed_by", "depends_on", 'eval: doc.status == "Done"', "Text"),
    ("Task", "completed_on", "depends_on", 'eval: doc.status == "Done"', "Text"),
    # AgileTask.set_completion_fields fills completed_on itself
    ("Task", "completed_on", "mandatory_depends_on", "", "Text"),
]


def after_install():
    ensure_customizations()
    migrate_legacy_task_statuses()
    recompute_all_project_progress()


def after_migrate():
    ensure_customizations()


def ensure_customizations():
    create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
    for doctype, fieldname, prop, value, property_type in PROPERTY_SETTERS:
        make_property_setter(
            doctype,
            fieldname,
            prop,
            value,
            property_type,
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
