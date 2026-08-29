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

import re

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
POINT_OPTIONS = {"1", "2", "3", "5", "8", "13"}
PRIORITIES = {"Low", "Medium", "High", "Urgent"}
FIRST_DATA_ROW = 2
MODIFIED_INDEX = FIELDS.index("modified")


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
            # Only ISO. getdate() would happily read 03/04/2026 month-first and
            # silently store the wrong date for anyone using a d/m/y sheet.
            if not ISO_DATE.match(value):
                errors.append(
                    _("{0} date '{1}' must be written as YYYY-MM-DD").format(label, value)
                )
                continue
            try:
                getdate(value)
            except Exception:
                errors.append(_("{0} date '{1}' is not a real date").format(label, value))
            else:
                clean[field] = value

    progress = raw.get("progress", "").strip()
    if progress:
        # NOT flt(): it returns 0 for junk instead of raising, which would
        # silently zero a task's progress from a typo
        number = _as_number(progress)
        if number is None:
            errors.append(_("Progress '{0}' is not a number").format(progress))
        elif number < 0 or number > 100:
            errors.append(_("Progress must be between 0 and 100"))
        else:
            clean["progress"] = number

    hours = raw.get("expected_time", "").strip()
    if hours:
        number = _as_number(hours)
        if number is None:
            errors.append(_("Estimated hours '{0}' is not a number").format(hours))
        elif number < 0:
            errors.append(_("Estimated hours cannot be negative"))
        else:
            clean["expected_time"] = number

    if "blocked_reason" in raw:
        clean["blocked_reason"] = raw.get("blocked_reason", "").strip()

    return clean, errors


def _as_number(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


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
        if not _same_cell(value, snapshot_fields.get(field, ""))
    }


def _same_cell(a, b):
    """Compare as the user sees it.

    UNFORMATTED_VALUE returns numbers for numeric cells while we push strings,
    so "40" vs 40.0 must not read as an edit or every numeric column would
    diff on every single tick.
    """
    a, b = str(a).strip(), str(b).strip()
    if a == b:
        return True
    na, nb = _as_number(a), _as_number(b)
    return na is not None and nb is not None and na == nb


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def _erp_changed_since(erp_modified, baseline):
    """Did ERPNext change this task after the value we last pushed?"""
    if not erp_modified or not baseline:
        return False
    return str(erp_modified)[:10] > str(baseline)[:10]


def _resolve_conflict(policy):
    """Which side wins when both changed. 'newest_wins' resolves to ERPNext
    because the sheet carries no per-cell timestamp to compare against."""
    if policy == "sheet_wins":
        return "sheet"
    return "erpnext"


def log(sync, outcome, task=None, field=None, old=None, new=None, reason=None, row=None):
    if task and not frappe.db.exists("Task", task):
        # a Link to a non-existent Task would raise and abort the whole cycle
        reason = f"{task}: {reason}" if reason else task
        task = None
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
        fields=LIST_FIELDS + ["description", "blocked_reason"],
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


def _empty_result(status, dry_run, message=None):
    """Every return path has the same shape — the UI reads these keys."""
    return {
        "status": status,
        "message": message,
        "dry_run": bool(dry_run),
        "inbound": {"applied": [], "rejected": [], "conflicts": [], "created": [], "skipped": []},
        "halted": None,
        "pushed": 0,
    }


def sync_sheet(sync_name, dry_run=False, force=False):
    """Run one full cycle for one Agile Sheet Sync record."""
    sync = frappe.get_doc("Agile Sheet Sync", sync_name)
    if not sync.enabled and not force:
        return _empty_result("disabled", dry_run)

    sheets, drive = client.get_services()

    meta = client.get_file_metadata(drive, sync.spreadsheet_id)
    if meta.get("trashed"):
        message = _("The spreadsheet is in Google Drive's bin. Restore it or disable this sync.")
        if not dry_run:
            _record_error(sync, message)
        # keep the shape every caller expects, so the UI never dereferences
        # an absent `inbound`
        return _empty_result("trashed", dry_run, message=message)

    version = str(meta.get("version") or "")
    unchanged = version and version == (sync.last_seen_version or "")

    result = {
        "status": "ok",
        "spreadsheet": meta.get("name"),
        "dry_run": bool(dry_run),
        "inbound": {"applied": [], "rejected": [], "conflicts": [], "created": [], "skipped": []},
        "halted": None,
        "pushed": 0,
    }

    snapshot = frappe.parse_json(sync.last_pushed_snapshot) if sync.last_pushed_snapshot else {}

    # With no baseline we cannot tell a human edit from stale sheet content, so
    # the first cycle is push-only. Without this, pointing a two-way sync at an
    # already-populated sheet imports the whole thing over live ERPNext data.
    seeding = not snapshot
    result["seeded"] = seeding
    if seeding and sync.direction == "two_way":
        result["message"] = _(
            "First sync for this sheet: it has been rebuilt from ERPNext and nothing was "
            "imported. Edits made in the sheet from now on will be picked up."
        )

    # ---- inbound ----
    if sync.direction == "two_way" and not seeding and (not unchanged or force):
        rows = client.get_values(sheets, sync.spreadsheet_id, data_range(sync.sheet_tab, FIRST_DATA_ROW))
        rows = pad_rows(rows.get("values", []))
        result["inbound"] = apply_inbound(sync, rows, snapshot, dry_run=dry_run)
        if result["inbound"].get("halted"):
            result["halted"] = result["inbound"]["halted"]
            result["status"] = "halted"
            return result

    # ---- outbound ----
    if not dry_run:
        pushed, skip_reason = push(sync, sheets, drive)
        result["pushed"] = pushed
        if skip_reason:
            result["push_skipped"] = skip_reason
            result["status"] = "push_skipped"
            log(sync, "halted", reason=skip_reason)
            _record_error(sync, skip_reason)
            _notify(sync, skip_reason)
            return result
        sync.db_set("last_error", None, update_modified=False)
    return result


def apply_inbound(sync, rows, snapshot, dry_run=False):
    """Write sheet edits back into ERPNext, one document at a time."""
    index, duplicates, new_rows, _blank = build_row_index(rows, FIRST_DATA_ROW)
    outcome = {"applied": [], "rejected": [], "conflicts": [], "created": [],
               "skipped": [], "halted": None}

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
        prior = snapshot.get(key)
        if prior is None:
            # a row we have never pushed: no baseline, so treat the sheet as
            # unknown rather than authoritative. The push will adopt it.
            outcome["skipped"].append({"task": key, "row": row_number})
            continue
        edited = changed_fields(raw, prior)
        if not edited:
            continue
        # conflict: changed on BOTH sides since our last push
        erp_modified = frappe.db.get_value("Task", key, "modified")
        baseline_modified = pad_rows([prior])[0][MODIFIED_INDEX]
        if _erp_changed_since(erp_modified, baseline_modified):
            decision = _resolve_conflict(sync.conflict_policy)
            outcome["conflicts"].append(
                {"task": key, "row": row_number, "resolution": decision,
                 "fields": sorted(edited.keys())}
            )
            if decision != "sheet":
                if not dry_run:
                    log(sync, "conflict", task=key, row=row_number,
                        reason=_("Changed in both places; kept the ERPNext value"))
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
    """Mirror ERPNext into the sheet, then re-watermark.

    Returns (rows_written, skip_reason). A skip is not an error: it means the
    push was refused because writing would have destroyed data.
    """
    tasks = read_tasks(sync.project)

    # read_tasks goes through get_list, so it is filtered by the acting user's
    # permissions. If that user quietly loses access, a blind push would clear
    # the sheet and look like "all the tasks were deleted".
    total = frappe.db.count("Task", {"project": sync.project, "is_group": 0, "is_template": 0})
    if total and len(tasks) < total:
        return 0, _(
            "Push skipped: {0} can only see {1} of this project's {2} tasks, and writing "
            "would have erased the rest from the sheet. Check that user's permissions."
        ).format(sync.sync_as_user, len(tasks), total)

    rows = [task_to_row(task) for task in tasks]

    previous = frappe.parse_json(sync.last_pushed_snapshot) if sync.last_pushed_snapshot else {}
    if previous and not rows:
        return 0, _(
            "Push skipped: ERPNext reports no tasks for this project but the sheet holds {0}. "
            "Refusing to blank the sheet."
        ).format(len(previous))

    # values.update writes only inside the existing grid and cannot add rows
    client.ensure_grid_size(sheets, sync.spreadsheet_id, sync.sheet_tab, FIRST_DATA_ROW + len(rows))

    # Capture the version BEFORE writing. Watermarking with the post-write
    # version would swallow any edit a human made during this cycle: it would
    # be overwritten by our write and then never read, because the next tick
    # would see "unchanged".
    pre = client.get_file_metadata(drive, sync.spreadsheet_id)

    data = [
        {"range": data_range(sync.sheet_tab, 1, 1), "values": [HEADERS]},
    ]
    if rows:
        data.append({"range": data_range(sync.sheet_tab, FIRST_DATA_ROW), "values": rows})
    client.batch_update_values(sheets, sync.spreadsheet_id, data)

    # values.update never clears below what it wrote, so a shrunk task list
    # would leave stale rows that the next read parses as live tasks
    tail_start = FIRST_DATA_ROW + len(rows)
    client.clear_values(sheets, sync.spreadsheet_id, data_range(sync.sheet_tab, tail_start))

    ensure_protection(sync, sheets)

    snapshot = {task["name"]: row for task, row in zip(tasks, rows)}
    sync.db_set("last_pushed_snapshot", frappe.as_json(snapshot), update_modified=False)
    sync.db_set("last_seen_version", str(pre.get("version") or ""), update_modified=False)
    sync.db_set("last_seen_modified", pre.get("modifiedTime"), update_modified=False)
    sync.db_set("last_synced_at", frappe.utils.now_datetime(), update_modified=False)
    return len(rows), None


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
    runs about every 4-5 minutes at best."""
    if not client.is_configured():
        return

    for name in frappe.get_all("Agile Sheet Sync", filters={"enabled": 1}, pluck="name"):
        try:
            run_scheduled(name)
        except Exception:
            # one broken sheet must not starve every other project for good
            frappe.log_error(
                title=f"Agile sheet sync failed: {name}",
                message=f"Sync {name} raised; continuing with the remaining sheets.",
            )


def run_scheduled(sync_name):
    """Background-job path: act as the configured user, not Administrator.

    Jobs run as Administrator, for whom check_app_permission() returns True
    unconditionally and document permissions are not enforced — a job would
    otherwise change tasks its owner cannot, and stamp completed_by as
    Administrator.
    """
    user = frappe.db.get_value("Agile Sheet Sync", sync_name, "sync_as_user")
    previous = frappe.session.user
    try:
        if user and user != previous:
            frappe.set_user(user)
        result = sync_sheet(sync_name)
        frappe.db.commit()
        return result
    except Exception as exc:
        frappe.db.rollback()
        _persist_failure(sync_name, exc)
        raise
    finally:
        if frappe.session.user != previous:
            frappe.set_user(previous)


def run_interactive(sync_name, dry_run=False, force=True):
    """Request path: run as the already-authenticated caller.

    Deliberately does NOT call frappe.set_user. In a web request set_user also
    resets form_dict and replaces session.sid/session.data in place — which
    corrupts the caller's live login session and can log them out.
    """
    try:
        result = sync_sheet(sync_name, dry_run=dry_run, force=force)
        if not dry_run:
            frappe.db.commit()
        return result
    except Exception as exc:
        frappe.db.rollback()
        if not dry_run:
            _persist_failure(sync_name, exc)
        raise


def _persist_failure(sync_name, exc):
    message = str(getattr(exc, "message", None) or exc)[:500]
    frappe.db.set_value(
        "Agile Sheet Sync", sync_name, "last_error", message, update_modified=False
    )
    frappe.db.commit()
