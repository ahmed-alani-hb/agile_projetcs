"""Two-way sync between ERPNext Tasks and a Google Sheet.

Shape of one cycle:

    metadata -> early exit if unchanged
    read + pad -> rebuild {task id: row} from the key column
    diff against the snapshot of what WE last wrote  (tells a human edit
        apart from our own write)
    apply inbound, one document at a time, behind a circuit breaker
    push outbound: batchUpdate then clear the tail
    re-read metadata and re-store the snapshot  (closes the feedback loop:
        our own write bumps modifiedTime, so without this every push would
        look like a user edit on the next tick)

Safety posture: never delete a Task because a row vanished, never coerce an
invalid cell, log the previous value of everything changed, and stop entirely
if one pull would rewrite more rows than the configured limit.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from agile_projects.api import normalize_task_dates
from agile_projects.google import client
from agile_projects.google.columns import (
    COLUMNS,
    FIELDS,
    HEADERS,
    KEY_INDEX,
    LAST_COLUMN,
    WIDTH,
    WRITABLE_FIELDS,
    build_row_index,
    data_range,
    pad_rows,
)
from agile_projects.overrides.task import AGILE_STATUSES
from agile_projects.views import LIST_FIELDS

POINT_OPTIONS = {"1", "2", "3", "5", "8", "13"}
PRIORITIES = {"Low", "Medium", "High", "Urgent"}
FIRST_DATA_ROW = 2


# ---------------------------------------------------------------------------
# Cell <-> field conversion (pure)
# ---------------------------------------------------------------------------


def cell(value):
    """Everything goes to the sheet as text: RAW input plus text cells means
    Google never reinterprets a value on the way in or out."""
    if value is None:
        return ""
    return str(value)


def task_to_row(task):
    row = []
    for field, _header, _writable in COLUMNS:
        value = task.get(field)
        if field in ("exp_start_date", "exp_end_date", "modified"):
            # dates are date-only in the sheet, mirroring the frontend's
            # toDateInput; v16 returns "YYYY-MM-DD HH:MM:SS"
            value = str(value)[:10] if value else ""
        elif field == "description" and value:
            value = frappe.utils.strip_html(str(value)).strip()[:500]
        row.append(cell(value))
    return row


def row_to_fields(row):
    """Writable cells of a sheet row, as raw strings."""
    out = {}
    for index, (field, _header, writable) in enumerate(COLUMNS):
        if writable:
            out[field] = str(row[index]).strip() if index < len(row) else ""
    return out


def validate_fields(raw, employee_exists=None):
    """Validate, never coerce. Returns (clean_fields, errors).

    `employee_exists` is injected so this stays testable without a database.
    """
    clean, errors = {}, []

    subject = raw.get("subject", "").strip()
    if subject:
        clean["subject"] = subject

    status = raw.get("status", "").strip()
    if status:
        if status not in AGILE_STATUSES:
            errors.append(_("Status '{0}' is not one of: {1}").format(status, ", ".join(AGILE_STATUSES)))
        else:
            clean["status"] = status

    priority = raw.get("priority", "").strip()
    if priority:
        if priority not in PRIORITIES:
            errors.append(_("Priority '{0}' is not valid").format(priority))
        else:
            clean["priority"] = priority

    points = raw.get("complexity_points", "").strip()
    if points:
        # a Select of strings in ERPNext, but Sheets hands back 5 or 5.0
        try:
            points = str(int(float(points)))
        except (TypeError, ValueError):
            points = points
        if points not in POINT_OPTIONS:
            errors.append(
                _("Points '{0}' is not one of: {1}").format(points, ", ".join(sorted(POINT_OPTIONS, key=int)))
            )
        else:
            clean["complexity_points"] = points

    sme = raw.get("sme_responsible", "").strip()
    if sme:
        if employee_exists and not employee_exists(sme):
            errors.append(_("No Employee with ID '{0}'").format(sme))
        else:
            clean["sme_responsible"] = sme

    for field, label in (("exp_start_date", _("Start")), ("exp_end_date", _("Due"))):
        value = raw.get(field, "").strip()
        if value:
            try:
                getdate(value)
            except Exception:
                errors.append(_("{0} date '{1}' could not be read").format(label, value))
            else:
                clean[field] = value

    progress = raw.get("progress", "").strip()
    if progress:
        try:
            number = flt(progress)
        except (TypeError, ValueError):
            errors.append(_("Progress '{0}' is not a number").format(progress))
        else:
            if number < 0 or number > 100:
                errors.append(_("Progress must be between 0 and 100"))
            else:
                clean["progress"] = number

    hours = raw.get("expected_time", "").strip()
    if hours:
        try:
            clean["expected_time"] = flt(hours)
        except (TypeError, ValueError):
            errors.append(_("Estimated hours '{0}' is not a number").format(hours))

    blocked = raw.get("blocked_reason", "").strip()
    if blocked or "blocked_reason" in raw:
        clean["blocked_reason"] = blocked

    return clean, errors


def changed_fields(sheet_fields, snapshot_row):
    """Which writable cells a human actually changed since our last write.

    Comparing against our own snapshot — not against ERPNext — is what stops
    the sync treating its own output as user input.
    """
    if snapshot_row is None:
        return dict(sheet_fields)
    snapshot_fields = row_to_fields(pad_rows([snapshot_row])[0])
    return {
        field: value
        for field, value in sheet_fields.items()
        if str(value).strip() != str(snapshot_fields.get(field, "")).strip()
    }


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def log(sync, outcome, task=None, field=None, old=None, new=None, reason=None, row=None):
    frappe.get_doc(
        {
            "doctype": "Agile Sheet Sync Log",
            "sheet_sync": sync.name,
            "project": sync.project,
            "task": task,
            "row_number": row,
            "outcome": outcome,
            "field": field,
            "old_value": None if old is None else str(old)[:500],
            "new_value": None if new is None else str(new)[:500],
            "reason": reason,
        }
    ).insert(ignore_permissions=True)


# ---------------------------------------------------------------------------
# The cycle
# ---------------------------------------------------------------------------


def read_tasks(project):
    """Every task in the project, unpaginated (mirrors get_timeline's shape)."""
    tasks = frappe.get_list(
        "Task",
        filters={"project": project, "is_group": 0, "is_template": 0},
        fields=LIST_FIELDS + ["description"],
        order_by="`tabTask`.`name` asc",
        limit_page_length=0,
    )
    employees = {t.sme_responsible for t in tasks if t.get("sme_responsible")}
    names = {}
    if employees:
        names = {
            e.name: e.employee_name
            for e in frappe.get_all(
                "Employee", filters={"name": ["in", list(employees)]},
                fields=["name", "employee_name"],
            )
        }
    for task in tasks:
        task["sme_name"] = names.get(task.get("sme_responsible")) or ""
    return tasks


def sync_sheet(sync_name, dry_run=False, force=False):
    """Run one full cycle for one Agile Sheet Sync record."""
    sync = frappe.get_doc("Agile Sheet Sync", sync_name)
    if not sync.enabled and not force:
        return {"status": "disabled"}

    sheets, drive = client.get_services()

    meta = client.get_file_metadata(drive, sync.spreadsheet_id)
    if meta.get("trashed"):
        message = _("The spreadsheet is in Google Drive's bin. Restore it or disable this sync.")
        _record_error(sync, message)
        return {"status": "trashed", "message": message}

    version = str(meta.get("version") or "")
    unchanged = version and version == (sync.last_seen_version or "")

    result = {
        "status": "ok",
        "spreadsheet": meta.get("name"),
        "dry_run": bool(dry_run),
        "inbound": {"applied": [], "rejected": [], "conflicts": [], "created": []},
        "halted": None,
        "pushed": 0,
    }

    snapshot = frappe.parse_json(sync.last_pushed_snapshot) if sync.last_pushed_snapshot else {}

    # ---- inbound ----
    if sync.direction == "two_way" and (not unchanged or force):
        rows = client.get_values(sheets, sync.spreadsheet_id, data_range(sync.sheet_tab, FIRST_DATA_ROW))
        rows = pad_rows(rows.get("values", []))
        result["inbound"] = apply_inbound(sync, rows, snapshot, dry_run=dry_run)
        if result["inbound"].get("halted"):
            result["halted"] = result["inbound"]["halted"]
            result["status"] = "halted"
            return result

    # ---- outbound ----
    if not dry_run:
        result["pushed"] = push(sync, sheets, drive)

    if not dry_run:
        sync.db_set("last_error", None, update_modified=False)
    return result


def apply_inbound(sync, rows, snapshot, dry_run=False):
    """Write sheet edits back into ERPNext, one document at a time."""
    index, duplicates, new_rows, _blank = build_row_index(rows, FIRST_DATA_ROW)
    outcome = {"applied": [], "rejected": [], "conflicts": [], "created": [], "halted": None}

    known = set(
        frappe.get_all(
            "Task", filters={"project": sync.project, "name": ["in", list(index.keys()) or [""]]},
            pluck="name",
        )
    ) if index else set()

    def employee_exists(name):
        return bool(frappe.db.exists("Employee", name))

    # ---- work out everything that would change, before changing anything ----
    planned = []
    for key, row_number in index.items():
        if key not in known:
            outcome["rejected"].append(
                {"task": key, "row": row_number, "error": _("No such task in this project")}
            )
            continue
        row = rows[row_number - FIRST_DATA_ROW]
        raw = row_to_fields(row)
        edited = changed_fields(raw, snapshot.get(key))
        if not edited:
            continue
        clean, errors = validate_fields(edited, employee_exists=employee_exists)
        if errors:
            outcome["rejected"].append({"task": key, "row": row_number, "error": "; ".join(errors)})
            continue
        if clean:
            planned.append((key, row_number, clean))

    created_rows = [r for r in new_rows]

    # ---- circuit breaker ----
    limit = cint(sync.max_changes_per_sync) or 25
    total = len(planned) + len(created_rows)
    if total > limit:
        message = _(
            "Halted: this sync would change {0} rows, which is over the limit of {1}. "
            "Nothing was written. Review the spreadsheet, then raise the limit or run a "
            "manual sync if the change is intended."
        ).format(total, limit)
        outcome["halted"] = message
        if not dry_run:
            log(sync, "halted", reason=message)
            _record_error(sync, message)
            _notify(sync, message)
        return outcome

    for key, row_number in duplicates.items():
        outcome["conflicts"].append(
            {"task": key, "rows": row_number, "error": _("Duplicate Task ID in the sheet; extra rows ignored")}
        )
        if not dry_run:
            log(sync, "conflict", task=key, reason=_("Duplicate row in sheet"), row=row_number[0])

    if dry_run:
        outcome["applied"] = [
            {"task": key, "row": row, "fields": fields} for key, row, fields in planned
        ]
        outcome["created"] = [{"row": r} for r in created_rows]
        return outcome

    # ---- apply, per document ----
    for key, row_number, fields in planned:
        _apply_one(sync, key, row_number, fields, outcome)

    for row_number in created_rows:
        _create_one(sync, rows[row_number - FIRST_DATA_ROW], row_number, outcome, employee_exists)

    return outcome


def _apply_one(sync, key, row_number, fields, outcome):
    savepoint = f"sheet_{frappe.generate_hash(length=8)}"
    # a stale message from a previous row would otherwise be reported here
    frappe.local.message_log = []
    try:
        frappe.db.savepoint(savepoint)
        doc = frappe.get_doc("Task", key)
        before = {field: doc.get(field) for field in fields}
        doc.update(normalize_task_dates(dict(fields)))
        doc.save()
        for field, value in fields.items():
            log(sync, "updated", task=key, field=field, old=before.get(field), new=value, row=row_number)
        outcome["applied"].append({"task": key, "row": row_number, "fields": fields})
    except Exception as exc:
        frappe.db.rollback(save_point=savepoint)
        from agile_projects.views import _clean_error

        reason = _clean_error(exc)
        log(sync, "rejected", task=key, reason=reason, row=row_number)
        outcome["rejected"].append({"task": key, "row": row_number, "error": reason})


def _create_one(sync, row, row_number, outcome, employee_exists):
    raw = row_to_fields(row)
    clean, errors = validate_fields(raw, employee_exists=employee_exists)
    if not clean.get("subject"):
        errors.append(_("A new row needs a Subject"))
    if errors:
        log(sync, "rejected", reason="; ".join(errors), row=row_number)
        outcome["rejected"].append({"task": None, "row": row_number, "error": "; ".join(errors)})
        return

    savepoint = f"sheet_new_{frappe.generate_hash(length=8)}"
    frappe.local.message_log = []
    try:
        frappe.db.savepoint(savepoint)
        clean.setdefault("status", "Backlog")
        doc = frappe.get_doc(
            dict(doctype="Task", project=sync.project, **normalize_task_dates(dict(clean)))
        ).insert()
        log(sync, "created", task=doc.name, new=doc.subject, row=row_number)
        outcome["created"].append({"task": doc.name, "row": row_number})
    except Exception as exc:
        frappe.db.rollback(save_point=savepoint)
        from agile_projects.views import _clean_error

        reason = _clean_error(exc)
        log(sync, "rejected", reason=reason, row=row_number)
        outcome["rejected"].append({"task": None, "row": row_number, "error": reason})


def push(sync, sheets, drive):
    """Mirror ERPNext into the sheet, then re-watermark."""
    tasks = read_tasks(sync.project)
    rows = [task_to_row(task) for task in tasks]

    data = [
        {"range": data_range(sync.sheet_tab, 1, 1), "values": [HEADERS]},
        {"range": data_range(sync.sheet_tab, FIRST_DATA_ROW), "values": rows or [[""] * WIDTH]},
    ]
    client.batch_update_values(sheets, sync.spreadsheet_id, data)

    # values.update never clears below what it wrote, so a shrunk task list
    # would leave stale rows that the next read parses as live tasks
    tail_start = FIRST_DATA_ROW + len(rows)
    client.clear_values(sheets, sync.spreadsheet_id, data_range(sync.sheet_tab, tail_start))

    ensure_protection(sync, sheets)

    # our own write bumped modifiedTime; re-read so the next tick does not
    # mistake it for a human edit
    meta = client.get_file_metadata(drive, sync.spreadsheet_id)
    snapshot = {task["name"]: row for task, row in zip(tasks, rows)}
    sync.db_set(
        {
            "last_pushed_snapshot": frappe.as_json(snapshot),
            "last_seen_version": str(meta.get("version") or ""),
            "last_seen_modified": meta.get("modifiedTime"),
            "last_synced_at": frappe.utils.now_datetime(),
        },
        update_modified=False,
    )
    return len(rows)


def ensure_protection(sync, sheets):
    """Protect the header row and the key column, once.

    This is a guardrail, not a boundary: the file owner can never be excluded
    from a protected range, and row insert/delete may not be blocked at all —
    which is exactly why identity comes from the key column, not row numbers.
    """
    if sync.protected_range_ids:
        return
    try:
        tabs = client.get_sheet_properties(sheets, sync.spreadsheet_id)
        sheet_id = tabs.get(sync.sheet_tab)
        if sheet_id is None:
            return
        email = client.service_account_email()
        editors = {"users": [email], "domainUsersCanEdit": False}
        requests = [
            {
                "addProtectedRange": {
                    "protectedRange": {
                        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                        "description": "Agile Projects sync: header",
                        # warningOnly would make `editors` be ignored, and a
                        # user who clicks through the warning orphans a row
                        "warningOnly": False,
                        "editors": editors,
                    }
                }
            },
            {
                "addProtectedRange": {
                    "protectedRange": {
                        "range": {"sheetId": sheet_id, "startColumnIndex": 0, "endColumnIndex": 1},
                        "description": "Agile Projects sync: Task ID column",
                        "warningOnly": False,
                        "editors": editors,
                    }
                }
            },
        ]
        response = client.batch_update(sheets, sync.spreadsheet_id, requests)
        ids = [
            r["addProtectedRange"]["protectedRange"]["protectedRangeId"]
            for r in response.get("replies", [])
            if r.get("addProtectedRange")
        ]
        # store them or every run would stack duplicate overlapping ranges
        sync.db_set("protected_range_ids", frappe.as_json(ids), update_modified=False)
    except Exception:
        # protection is a nicety; never fail a sync because of it
        frappe.log_error(
            title="Agile sheet protection failed", message=frappe.get_traceback()
        )


def _record_error(sync, message):
    sync.db_set("last_error", message, update_modified=False)


def _notify(sync, message):
    try:
        frappe.publish_realtime(
            "agile_sheet_sync_halted", {"project": sync.project, "message": message}
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Scheduler entry point
# ---------------------------------------------------------------------------


def sync_all_sheets():
    """Scheduled entry point. v16's default scheduler tick is 240s, so this
    runs about every 4 minutes at best."""
    if not client.is_configured():
        return

    for name in frappe.get_all("Agile Sheet Sync", filters={"enabled": 1}, pluck="name"):
        run_as_configured_user(name)


def run_as_configured_user(sync_name, dry_run=False, force=False):
    """Run a sync as its configured user, not as Administrator.

    Background jobs run as Administrator, for whom check_app_permission()
    returns True unconditionally and document permissions are not enforced —
    so a job would silently be able to change tasks its owner cannot, and
    would stamp completed_by as Administrator.
    """
    user = frappe.db.get_value("Agile Sheet Sync", sync_name, "sync_as_user")
    previous = frappe.session.user
    try:
        if user and user != previous:
            frappe.set_user(user)
        result = sync_sheet(sync_name, dry_run=dry_run, force=force)
        if not dry_run:
            frappe.db.commit()
        return result
    except Exception as exc:
        frappe.db.rollback()
        message = str(getattr(exc, "message", None) or exc)
        frappe.db.set_value("Agile Sheet Sync", sync_name, "last_error", message[:500],
                            update_modified=False)
        frappe.db.commit()
        frappe.log_error(title=f"Agile sheet sync failed: {sync_name}", message=frappe.get_traceback())
        raise
    finally:
        if frappe.session.user != previous:
            frappe.set_user(previous)
