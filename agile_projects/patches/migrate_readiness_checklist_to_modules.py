"""Promote every ERP Module Readiness Checklist row to an Agile Module.

MUST stay under [post_model_sync]. Frappe's `get_patches_from_app` treats a
patches.txt with no section headers as pre-model-sync only, so a bare line here
would run before `Agile Module` is synced, no-op against a missing doctype, and
then be written to the Patch Log and never retried.

The work itself lives in setup/install.py so `after_install` can reuse it.
"""

import frappe

from agile_projects.setup.install import migrate_checklist_to_modules


def execute():
    if not frappe.db.exists("DocType", "Agile Module"):
        return
    created = migrate_checklist_to_modules()
    if created:
        print(f"agile_projects: created {created} Agile Module(s) from readiness checklist rows")
