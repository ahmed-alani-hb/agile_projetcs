"""Google Sheets / Drive access for the sync, via a single service account.

Frappe v16 already ships google-api-python-client, google-auth and
google-auth-oauthlib, so nothing extra needs installing.

Deliberately NOT here: `spreadsheets.create`. Service accounts have no Drive
storage quota (creating a file commonly returns 403 storageQuotaExceeded even
on an empty Drive) and an SA-created file is owned by a principal no human can
sign in as, with no way to transfer ownership back on consumer accounts. A
human creates the spreadsheet and shares it with the service account.
"""

import random
import time

import frappe
from frappe import _

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    # metadata only — enough for files.get(modifiedTime) and strictly less
    # access than drive.readonly
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]

MAX_ATTEMPTS = 5
MAX_BACKOFF_SECONDS = 32
# only these are worth retrying; 400/401/403/404 fail identically forever and
# retrying them just burns the shared per-service-account quota
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class SheetSyncError(frappe.ValidationError):
    """A Google-side failure already translated into something a human can act on."""


def is_configured():
    """True when a key is stored and the integration is switched on."""
    settings = frappe.get_cached_doc("Agile Google Settings")
    if not settings.enabled:
        return False
    return bool(settings.get_password("service_account_json", raise_exception=False))


def _load_key():
    """Return the parsed key, or throw. Isolated so no frame that can raise
    later still holds the plaintext.

    This matters: frappe.log_error() renders the traceback WITH frame
    variables, and its sanitiser only redacts names matching password/secret/
    token/key — not `raw`, not `info`, and not the dict key `private_key`. A
    credential failure raised from a frame holding the key would therefore
    write it to the Error Log in cleartext.
    """
    settings = frappe.get_cached_doc("Agile Google Settings")
    if not settings.enabled:
        frappe.throw(_("Google Sheets sync is not enabled in Agile Google Settings."), SheetSyncError)

    key_json = settings.get_password("service_account_json", raise_exception=False)
    if not key_json:
        frappe.throw(_("No service account key has been configured."), SheetSyncError)

    parsed = None
    try:
        parsed = frappe.parse_json(key_json)
    except Exception:
        parsed = None
    finally:
        del key_json
    if not isinstance(parsed, dict):
        frappe.throw(_("The stored service account key is not valid JSON."), SheetSyncError)
    return parsed


def get_credentials():
    try:
        from google.oauth2 import service_account
    except ImportError:
        frappe.throw(
            _("google-auth is not available on this bench. Run `bench setup requirements`."),
            SheetSyncError,
        )

    info = _load_key()
    failed = False
    try:
        # no `subject=` — that is domain-wide delegation, which is not needed
        # when the sheet is shared with the service account directly
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    except Exception:
        failed = True
    finally:
        info = None
        del info
    if failed:
        # raised outside the frame that held the key, and deliberately without
        # echoing the underlying exception text
        frappe.throw(
            _(
                "Google rejected the service account key. Check that the JSON key is complete "
                "and has not been revoked."
            ),
            SheetSyncError,
        )


def get_services():
    """(sheets, drive) API clients."""
    from googleapiclient.discovery import build

    creds = get_credentials()
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    return sheets, drive


def service_account_email():
    settings = frappe.get_cached_doc("Agile Google Settings")
    return settings.service_account_email or _("the sync service account")


# ---------------------------------------------------------------------------
# Execution with backoff + human-readable errors
# ---------------------------------------------------------------------------


def execute(request, _sleep=time.sleep):
    """Run a googleapiclient request with truncated exponential backoff.

    Google prescribes min((2**n) + jitter, max_backoff); the jitter matters so
    that many sheets syncing on the same tick don't retry in lockstep.
    """
    last_exc = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            return request.execute()
        except Exception as exc:
            status = _status_of(exc)
            last_exc = exc
            if status not in RETRYABLE_STATUS or attempt == MAX_ATTEMPTS - 1:
                raise translate_error(exc)
            _sleep(min(2**attempt + random.random(), MAX_BACKOFF_SECONDS))
    raise translate_error(last_exc)


def _status_of(exc):
    resp = getattr(exc, "resp", None)
    status = getattr(resp, "status", None)
    if status is None:
        status = getattr(exc, "status_code", None)
    try:
        return int(status)
    except (TypeError, ValueError):
        return None


def _reason_of(exc):
    """Google returns the actionable detail in the body, not the status."""
    blob = ""
    content = getattr(exc, "content", None)
    if content:
        blob = content.decode() if isinstance(content, bytes) else str(content)
    return f"{blob} {exc}".lower()


def translate_error(exc):
    """Map a Google API failure onto a message that names the fix.

    The statuses overlap (403 is used for permissions, quota AND storage), so
    branch on the reason text rather than the status alone.
    """
    if isinstance(exc, SheetSyncError):
        return exc

    status = _status_of(exc)
    reason = _reason_of(exc)
    email = service_account_email()

    if status == 403 and "storagequotaexceeded" in reason:
        message = _(
            "Google refused to create a file as the sync account. Create the spreadsheet "
            "yourself and share it with {0} instead."
        ).format(email)
    elif status == 403 and "accessnotconfigured" in reason:
        message = _(
            "The Google Sheets or Drive API is not enabled on the Cloud project for this "
            "service account. Enable both APIs, then try again."
        )
    elif status == 403 and ("ratelimit" in reason or "userratelimit" in reason):
        message = _("Google rate limit reached. The next scheduled sync will retry.")
    elif status == 403:
        message = _(
            "{0} can no longer edit this spreadsheet. Re-share it with that address as an Editor."
        ).format(email)
    elif status == 404:
        message = _(
            "Spreadsheet not found. It may have been deleted, or it was never shared with {0}."
        ).format(email)
    elif status == 400 and "unable to parse range" in reason:
        message = _(
            "The tab named in this sync no longer exists in the spreadsheet. "
            "Rename it back, or update the Sheet Tab field."
        )
    elif status == 400 and "tried writing to row" in reason:
        message = _("The spreadsheet tab does not have enough rows for this project. Add rows and sync again.")
    elif status == 400 and "no grid with id" in reason:
        message = _("The spreadsheet tab was recreated. Run the sync again to re-detect it.")
    elif status == 429:
        message = _("Google rate limit reached. The next scheduled sync will retry.")
    elif status == 401:
        message = _(
            "Google rejected the credentials for {0}. The key may have been revoked, or this "
            "server's clock may be out of sync."
        ).format(email)
    else:
        message = _("Google API error: {0}").format(str(exc)[:400])

    return SheetSyncError(message)


# ---------------------------------------------------------------------------
# Thin wrappers used by the sync engine
# ---------------------------------------------------------------------------


def get_file_metadata(drive, spreadsheet_id):
    """version/modifiedTime are the cheap change signal; trashed does NOT 404."""
    return execute(
        drive.files().get(
            fileId=spreadsheet_id,
            fields="id,name,modifiedTime,version,trashed",
            supportsAllDrives=True,
        )
    )


def get_values(sheets, spreadsheet_id, a1_range):
    return execute(
        sheets.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=a1_range,
            # FORMATTED_VALUE would return locale-formatted strings and
            # SERIAL_NUMBER would hand us 1899-12-30 epoch floats
            valueRenderOption="UNFORMATTED_VALUE",
            dateTimeRenderOption="FORMATTED_STRING",
            majorDimension="ROWS",
        )
    )


def batch_update_values(sheets, spreadsheet_id, data):
    """One quota unit for many ranges. RAW so Google never reinterprets input."""
    return execute(
        sheets.spreadsheets()
        .values()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "RAW", "data": data},
        )
    )


def clear_values(sheets, spreadsheet_id, a1_range):
    """Clears values but keeps formatting and data validation."""
    return execute(
        sheets.spreadsheets()
        .values()
        .clear(spreadsheetId=spreadsheet_id, range=a1_range, body={})
    )


def get_sheet_grid(sheets, spreadsheet_id):
    """tab title -> full properties, including gridProperties.

    values.update writes only INSIDE the existing grid — unlike append it
    cannot add rows — so a project with more tasks than the tab has rows fails
    with a 400 unless the grid is grown first.
    """
    result = execute(
        sheets.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="sheets.properties(sheetId,title,gridProperties(rowCount,columnCount))",
        )
    )
    return {
        sheet["properties"]["title"]: sheet["properties"]
        for sheet in result.get("sheets", [])
        if sheet.get("properties")
    }


def get_sheet_properties(sheets, spreadsheet_id):
    """Resolve tab title -> numeric sheetId, which batchUpdate needs."""
    return {title: props["sheetId"] for title, props in get_sheet_grid(sheets, spreadsheet_id).items()}


def ensure_grid_size(sheets, spreadsheet_id, tab, needed_rows):
    """Grow the tab if the write would run past the last row of the grid."""
    grid = get_sheet_grid(sheets, spreadsheet_id)
    props = grid.get(tab)
    if not props:
        return None
    current = (props.get("gridProperties") or {}).get("rowCount") or 0
    if needed_rows > current:
        batch_update(
            sheets,
            spreadsheet_id,
            [
                {
                    "appendDimension": {
                        "sheetId": props["sheetId"],
                        "dimension": "ROWS",
                        "length": needed_rows - current + 100,
                    }
                }
            ],
        )
    return props["sheetId"]


def batch_update(sheets, spreadsheet_id, requests):
    return execute(
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests}
        )
    )
