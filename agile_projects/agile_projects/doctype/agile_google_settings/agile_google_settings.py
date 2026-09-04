import frappe
from frappe import _
from frappe.model.document import Document


class AgileGoogleSettings(Document):
    def validate(self):
        self.service_account_email = None
        raw = self.get_password("service_account_json", raise_exception=False)
        if not raw:
            if self.enabled:
                frappe.throw(_("Paste a service account JSON key before enabling the sync."))
            return

        try:
            info = frappe.parse_json(raw)
        except Exception:
            frappe.throw(_("The service account key is not valid JSON."))

        if not isinstance(info, dict) or info.get("type") != "service_account":
            frappe.throw(
                _("That JSON is not a service account key (expected \"type\": \"service_account\").")
            )
        for field in ("client_email", "private_key", "token_uri"):
            if not info.get(field):
                frappe.throw(_("The service account key is missing {0}.").format(field))

        # surfaced read-only so an admin knows which address to share sheets with
        self.service_account_email = info["client_email"]
