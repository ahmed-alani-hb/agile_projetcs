"""Whitelisted endpoints for configuring and running the Sheets sync."""

import frappe
from frappe import _

from agile_projects.api import _ensure_app_access
from agile_projects.google import client, sheet_sync


def _manager_only():
    _ensure_app_access()
    roles = set(frappe.get_roles())
    if frappe.session.user != "Administrator" and not roles & {"System Manager", "Projects Manager"}:
        frappe.throw(
            _("Only a Projects Manager or System Manager can configure the Google Sheets sync."),
            frappe.PermissionError,
        )


@frappe.whitelist()
def get_settings():
    """Whether the integration is usable, and which address to share sheets with.

    Never returns the key itself.
    """
    _ensure_app_access()
    settings = frappe.get_cached_doc("Agile Google Settings")
    return {
        "enabled": bool(settings.enabled),
        "configured": client.is_configured(),
        "service_account_email": settings.service_account_email,
    }


@frappe.whitelist()
def get_sync_config(project):
    _ensure_app_access()
    frappe.has_permission("Project", doc=project, throw=True)

    name = frappe.db.exists("Agile Sheet Sync", {"project": project})
    config = None
    if name:
        doc = frappe.get_doc("Agile Sheet Sync", name)
        config = {
            "name": doc.name,
            "project": doc.project,
            "enabled": bool(doc.enabled),
            "direction": doc.direction,
            "spreadsheet_id": doc.spreadsheet_id,
            "sheet_tab": doc.sheet_tab,
            "sync_as_user": doc.sync_as_user,
            "conflict_policy": doc.conflict_policy,
            "max_changes_per_sync": doc.max_changes_per_sync,
            "last_synced_at": doc.last_synced_at,
            "last_error": doc.last_error,
            "url": f"https://docs.google.com/spreadsheets/d/{doc.spreadsheet_id}/edit",
        }
    return {"config": config, "settings": get_settings()}


@frappe.whitelist(methods=["POST"])
def save_sync_config(
    project,
    spreadsheet_id,
    sheet_tab="Tasks",
    direction="push",
    enabled=0,
    conflict_policy="erpnext_wins",
    max_changes_per_sync=25,
    sync_as_user=None,
):
    _manager_only()
    frappe.has_permission("Project", ptype="write", doc=project, throw=True)

    name = frappe.db.exists("Agile Sheet Sync", {"project": project})
    doc = frappe.get_doc("Agile Sheet Sync", name) if name else frappe.new_doc("Agile Sheet Sync")
    doc.update(
        {
            "project": project,
            "spreadsheet_id": spreadsheet_id,
            "sheet_tab": sheet_tab or "Tasks",
            "direction": direction,
            "enabled": frappe.utils.cint(enabled),
            "conflict_policy": conflict_policy,
            "max_changes_per_sync": frappe.utils.cint(max_changes_per_sync) or 25,
            "sync_as_user": sync_as_user or frappe.session.user,
        }
    )
    doc.save()
    return get_sync_config(project)


@frappe.whitelist(methods=["POST"])
def sync_now(project, dry_run=0):
    """Manual sync. A dry run reports the full diff and writes nothing."""
    _ensure_app_access()
    frappe.has_permission("Project", ptype="write", doc=project, throw=True)

    name = frappe.db.exists("Agile Sheet Sync", {"project": project})
    if not name:
        frappe.throw(_("This project has no Google Sheet configured yet."))

    return sheet_sync.run_as_configured_user(
        name, dry_run=frappe.utils.cint(dry_run), force=True
    )


@frappe.whitelist()
def get_sync_log(project, limit=50):
    _ensure_app_access()
    frappe.has_permission("Project", doc=project, throw=True)
    return frappe.get_all(
        "Agile Sheet Sync Log",
        filters={"project": project},
        fields=["name", "task", "row_number", "outcome", "field", "old_value", "new_value",
                "reason", "creation"],
        order_by="creation desc",
        limit_page_length=frappe.utils.cint(limit) or 50,
    )


@frappe.whitelist(methods=["POST"])
def test_connection(project):
    """Confirm the sheet is reachable and writable before enabling a sync."""
    _manager_only()
    name = frappe.db.exists("Agile Sheet Sync", {"project": project})
    if not name:
        frappe.throw(_("Save the spreadsheet ID first."))
    doc = frappe.get_doc("Agile Sheet Sync", name)

    sheets, drive = client.get_services()
    meta = client.get_file_metadata(drive, doc.spreadsheet_id)
    tabs = client.get_sheet_properties(sheets, doc.spreadsheet_id)
    return {
        "name": meta.get("name"),
        "trashed": bool(meta.get("trashed")),
        "tabs": sorted(tabs.keys()),
        "tab_found": doc.sheet_tab in tabs,
        "service_account_email": client.service_account_email(),
    }
