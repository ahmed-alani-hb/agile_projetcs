import frappe
from frappe.model.document import Document


class AgileSavedView(Document):
    def validate(self):
        if self.is_default:
            # only one default per user + project + view type
            existing = frappe.get_all(
                "Agile Saved View",
                filters={
                    "user": self.user,
                    "view_type": self.view_type,
                    "is_default": 1,
                    "name": ["!=", self.name],
                },
                pluck="name",
            )
            for name in existing:
                if frappe.db.get_value("Agile Saved View", name, "project") == self.project:
                    frappe.db.set_value("Agile Saved View", name, "is_default", 0)
