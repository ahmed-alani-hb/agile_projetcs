"""A day's worth of a project's numbers, frozen.

Per-status flow (cumulative flow, time-in-status) cannot be reconstructed after
the fact — Task versioning only began in Phase 3 and nothing recorded the past
before that. This doctype is how that history starts existing: one row per
project per day, written by `metrics.snapshot_all_projects`.

Deliberately not versioned (`track_changes: 0`): it *is* the history, so
versioning it would only record a job overwriting today's row.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class AgileMetricSnapshot(Document):
    def validate(self):
        # One row per project per day is the contract every reader relies on.
        duplicate = frappe.db.exists(
            "Agile Metric Snapshot",
            {
                "project": self.project,
                "snapshot_date": self.snapshot_date,
                "name": ["!=", self.name or ""],
            },
        )
        if duplicate:
            frappe.throw(
                _("A snapshot for {0} on {1} already exists.").format(
                    self.project, self.snapshot_date
                ),
                frappe.DuplicateEntryError,
            )
