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
        self._reset_state_on_repoint()
        self._validate_sync_user()

    def _reset_state_on_repoint(self):
        """Pointing at a different sheet or tab invalidates the baseline.

        Without this, a stale snapshot is diffed against a different
        spreadsheet and its rows are imported over live data; and the stored
        protected-range ids refer to ranges in the OLD file, so the new one
        would never get its key column protected.
        """
        if self.is_new():
            return
        if self.has_value_changed("spreadsheet_id") or self.has_value_changed("sheet_tab"):
            self.last_pushed_snapshot = None
            self.last_seen_version = None
            self.last_seen_modified = None
            self.protected_range_ids = None

    def _validate_sync_user(self):
        if self.sync_as_user == "Administrator":
            frappe.throw(
                _(
                    "Pick a real user for 'Sync As User'. Administrator bypasses document "
                    "permissions, so a scheduled sync would be able to change tasks nobody "
                    "on this project is allowed to touch."
                )
            )

        # Stops a Projects Manager pointing the sync at a more privileged
        # identity and writing tasks they could not write themselves.
        if self.sync_as_user != frappe.session.user and "System Manager" not in frappe.get_roles():
            frappe.throw(
                _("Only a System Manager can set the sync to run as somebody else.")
            )

        roles = set(frappe.get_roles(self.sync_as_user))
        if not roles & {"System Manager", "Projects Manager", "Projects User"}:
            frappe.throw(
                _("{0} has no Projects role, so the sync would not be able to read this project.")
                .format(self.sync_as_user)
            )


def extract_spreadsheet_id(value):
    """Accept a full spreadsheet URL as well as a bare id."""
    value = (value or "").strip()
    if "/spreadsheets/d/" in value:
        value = value.split("/spreadsheets/d/", 1)[1]
        value = value.split("/", 1)[0]
    return value
