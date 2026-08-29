import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class AgileSheetSync(Document):
    def validate(self):
        self.spreadsheet_id = extract_spreadsheet_id(self.spreadsheet_id)
        if cint(self.max_changes_per_sync) <= 0:
            self.max_changes_per_sync = 25
        if not self.sync_as_user:
            self.sync_as_user = frappe.session.user
        if self.sync_as_user == "Administrator":
            frappe.throw(
                _(
                    "Pick a real user for 'Sync As User'. Administrator bypasses document "
                    "permissions, so a scheduled sync would be able to change tasks nobody "
                    "on this project is allowed to touch."
                )
            )


def extract_spreadsheet_id(value):
    """Accept a full spreadsheet URL as well as a bare id."""
    value = (value or "").strip()
    if "/spreadsheets/d/" in value:
        value = value.split("/spreadsheets/d/", 1)[1]
        value = value.split("/", 1)[0]
    return value
