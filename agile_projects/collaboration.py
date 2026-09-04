"""Discussion, assignment and evidence.

Until now the app could plan work and enforce how it advanced, but two people
had no way to talk about any of it inside the system: no comments, no
assignment the SPA could create, nowhere to put a sign-off screenshot, and no
record of who changed what. Decisions lived in chat; evidence lived in email.

Everything here is built on Frappe's own primitives — `Comment`, `ToDo` (via
`assign_to`), `File`, `Version` and `Notification Log` — so anything written
from the SPA is visible in Desk and vice versa.

Conventions match `agile_projects/modules.py`: `_ensure_app_access()` first,
then a per-document permission check, and writes are POST-only.
"""

import json
import re

import frappe
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import (
    enqueue_create_notification,
)
from frappe.desk.form import assign_to
from frappe.utils import cint, get_fullname, sanitize_html, strip_html

from agile_projects.api import ALLOWED_ROLES, _ensure_app_access

# Every endpoint below takes a (doctype, name) pair from the client. Without
# this allowlist `get_comments` would be a read primitive over every doctype on
# the site — the reference is checked against it *before* anything else.
COMMENTABLE = ("Task", "Agile Module", "Cutover Step", "Project")

# The human name of a referenced document, for notification subjects.
REFERENCE_TITLE_FIELD = {
    "Task": "subject",
    "Agile Module": "module_name",
    "Cutover Step": "title",
    "Project": "project_name",
}

MANAGER_ROLES = {"System Manager", "Projects Manager"}

# Fields whose changes are noise in a timeline: framework bookkeeping, and the
# two ordering columns the boards write on every drag.
UNINTERESTING_FIELDS = {
    "modified",
    "modified_by",
    "docstatus",
    "idx",
    "board_order",
    "gate_order",
    "_assign",
    "_comments",
    "_liked_by",
    "_user_tags",
    "_seen",
    "lft",
    "rgt",
    "old_parent",
}

FIELD_LABELS = {
    "status": "status",
    "priority": "priority",
    "subject": "subject",
    "description": "description",
    "complexity_points": "complexity points",
    "sme_responsible": "SME",
    "exp_start_date": "start date",
    "exp_end_date": "due date",
    "expected_time": "expected hours",
    "progress": "progress",
    "blocked_reason": "blocked reason",
    "agile_module": "module",
    "project": "project",
    "gate": "gate",
    "configuration_status": "configuration status",
    "data_migration_status": "data migration status",
    "functional_signoff": "functional sign-off",
    "target_go_live": "target go-live",
    "system_platform": "platform",
    "step_order": "position",
    "planned_start": "planned start",
    "planned_end": "planned end",
    "actual_start": "actual start",
    "actual_end": "actual end",
    "depends_on": "dependency",
}

CHECK_FIELDS = {"functional_signoff"}

MAX_VALUE_CHARS = 60


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def _check_reference(doctype, name, ptype="read"):
    """Validate the (doctype, name) pair a client handed us, then permission it.

    Order matters: the allowlist runs before the permission check so an
    unexpected doctype is refused outright rather than probed.
    """
    if doctype not in COMMENTABLE:
        frappe.throw(
            _("{0} does not support collaboration").format(doctype), frappe.PermissionError
        )
    if not name:
        frappe.throw(_("A document is required"), frappe.ValidationError)
    if not frappe.db.exists(doctype, name):
        frappe.throw(_("{0} {1} not found").format(doctype, name), frappe.DoesNotExistError)
    frappe.has_permission(doctype, ptype=ptype, doc=name, throw=True)


def _is_manager():
    return frappe.session.user == "Administrator" or bool(
        MANAGER_ROLES & set(frappe.get_roles())
    )


def _reference_title(doctype, name):
    field = REFERENCE_TITLE_FIELD.get(doctype)
    return (field and frappe.db.get_value(doctype, name, field)) or name


def _reference_project(doctype, name):
    if doctype == "Project":
        return name
    return frappe.db.get_value(doctype, name, "project")


def _spa_link(doctype, name, project=None):
    """Deep link into the SPA, so a notification is worth clicking."""
    if doctype == "Project":
        return f"/agile/projects/{name}"
    project = project or _reference_project(doctype, name)
    if not project:
        return None
    if doctype == "Task":
        # ProjectDetail opens the drawer when ?task= is present.
        return f"/agile/projects/{project}?task={name}"
    if doctype == "Agile Module":
        return f"/agile/projects/{project}/modules"
    if doctype == "Cutover Step":
        return f"/agile/projects/{project}/cutover"
    return None


def _attach_users(rows, key="owner"):
    """Resolve user ids to names and avatars in one query, not one per row.

    Mirrors api._attach_employee_info; these rows are Users rather than
    Employees because a Comment's author is whoever was logged in.
    """
    ids = {row.get(key) for row in rows if row.get(key)}
    if not ids:
        return
    users = {
        u.name: u
        for u in frappe.get_all(
            "User",
            filters={"name": ["in", list(ids)]},
            fields=["name", "full_name", "user_image"],
        )
    }
    for row in rows:
        user = users.get(row.get(key))
        row["user_name"] = user.full_name if user else row.get(key)
        row["user_image"] = user.user_image if user else None


# ---------------------------------------------------------------------------
# Mentions — pure, so it is unit-tested without a bench
# ---------------------------------------------------------------------------

_SPAN_TAG = re.compile(r"<span\b[^>]*>", re.IGNORECASE)
_IS_MENTION = re.compile(
    r'data-type\s*=\s*["\']mention["\']|class\s*=\s*["\'][^"\']*\bmention\b', re.IGNORECASE
)
_DATA_ID = re.compile(r'data-id\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)


def extract_mentions(html):
    """User ids @mentioned in a comment body, in order, without duplicates.

    Tiptap renders a mention as `<span data-type="mention" data-id="a@b.com">`.
    Parsed with a regex rather than a Frappe internal so the behaviour is ours
    and testable, and run against the *raw* input rather than the sanitised
    copy — whether the sanitiser keeps `data-*` attributes is not something
    this feature should depend on.
    """
    if not html:
        return []
    found = []
    for tag in _SPAN_TAG.findall(html):
        if not _IS_MENTION.search(tag):
            continue
        match = _DATA_ID.search(tag)
        if not match:
            continue
        user = match.group(1).strip()
        if user and user not in found:
            found.append(user)
    return found


# ---------------------------------------------------------------------------
# Sanitising a comment body — pure, and load-bearing
# ---------------------------------------------------------------------------

# Stripped before sanitising, tag and content together.
_DANGEROUS = "script|style|iframe|object|embed|base|meta|link|form|noscript"
_DANGEROUS_BLOCK = re.compile(
    rf"<\s*({_DANGEROUS})\b[^>]*>.*?<\s*/\s*\1\s*>", re.IGNORECASE | re.DOTALL
)
_DANGEROUS_TAG = re.compile(rf"<\s*/?\s*({_DANGEROUS})\b[^>]*>", re.IGNORECASE)


def clean_comment_html(raw):
    """Sanitise a comment body for storage.

    Two layers, because `frappe.utils.sanitize_html` on its own is not enough
    for this input. Read its source: with the default `always_sanitize=False`
    it returns the string *untouched* when `is_json(html)` is true, so a body
    that happens to parse as JSON is stored raw — and this is then rendered
    with `v-html`. Its allowlist also keeps `style`, SVG and MathML elements,
    which is reasonable for the trusted Desk paths it was written for and not
    for a comment box.

    So: strip the dangerous elements outright first, then sanitise with
    `always_sanitize=True` so no short-circuit can apply.
    """
    text = _DANGEROUS_BLOCK.sub("", str(raw or ""))
    text = _DANGEROUS_TAG.sub("", text)
    return sanitize_html(text, always_sanitize=True)


# ---------------------------------------------------------------------------
# Activity formatting — also pure
# ---------------------------------------------------------------------------


def _humanise_field(fieldname):
    return FIELD_LABELS.get(fieldname) or fieldname.replace("_", " ").strip().lower()


def _humanise_value(fieldname, value):
    if fieldname in CHECK_FIELDS:
        return "ticked" if cint(value) else "unticked"
    if value is None or value == "":
        return ""
    text = strip_html(str(value)).strip()
    if len(text) > MAX_VALUE_CHARS:
        text = text[:MAX_VALUE_CHARS].rstrip() + "…"
    return text


def describe_version(data):
    """Turn a Version row's `data` JSON into human sentences.

    `changed` is a list of [fieldname, old, new]. Child-table churn (`added`,
    `removed`, `row_changed`) is summarised rather than enumerated — a task's
    dependency table changing is worth one line, not one per column.
    """
    if isinstance(data, str):
        try:
            data = json.loads(data or "{}")
        except (ValueError, TypeError):
            return []
    if not isinstance(data, dict):
        return []

    lines = []
    for change in data.get("changed") or []:
        if not isinstance(change, (list, tuple)) or len(change) < 3:
            continue
        fieldname, old, new = change[0], change[1], change[2]
        if fieldname in UNINTERESTING_FIELDS:
            continue
        label = _humanise_field(fieldname)
        old_text = _humanise_value(fieldname, old)
        new_text = _humanise_value(fieldname, new)
        if old_text == new_text:
            continue
        if fieldname in CHECK_FIELDS:
            lines.append(f"{new_text} {label}")
        elif not old_text:
            lines.append(f"set {label} to {new_text}")
        elif not new_text:
            lines.append(f"cleared {label}")
        else:
            lines.append(f"changed {label} from {old_text} to {new_text}")

    for key, verb in (("added", "added"), ("removed", "removed")):
        rows = data.get(key) or []
        by_table = {}
        for row in rows:
            if isinstance(row, (list, tuple)) and row:
                by_table[row[0]] = by_table.get(row[0], 0) + 1
        for table, count in by_table.items():
            lines.append(f"{verb} {count} {_humanise_field(table)} row{'' if count == 1 else 's'}")

    return lines


# ---------------------------------------------------------------------------
# Who can be mentioned or assigned
# ---------------------------------------------------------------------------

# Defensive cap; the picker also filters client-side, as the rest of the app does.
MAX_MENTIONABLE = 500


@frappe.whitelist()
def get_mentionable_users(txt=""):
    """Users who can actually open this app.

    A mention target is a User, not an Employee. Going via Employee — as the
    first version of this did — silently loses two groups: employees whose
    optional `user_id` link is blank (the common case on a fresh ERPNext), and
    anyone with app access who has no Employee record at all, such as a
    Projects Manager or an admin.

    Roles are the honest scope here: Frappe permissions on Project are
    role-based rather than per-document, so there is no per-project user list
    to draw from. Over-listing is safe — `add_comment` re-checks
    `has_permission(..., user=...)` before notifying anyone, so the picker is a
    convenience and the server stays the gate.
    """
    _ensure_app_access()

    holders = frappe.get_all(
        "Has Role",
        filters={"parenttype": "User", "role": ["in", sorted(ALLOWED_ROLES)]},
        pluck="parent",
        distinct=True,
        limit_page_length=0,
    )
    if not holders:
        return []

    filters = {"name": ["in", holders], "enabled": 1, "user_type": "System User"}
    or_filters = None
    if txt:
        or_filters = [
            ["User", "full_name", "like", f"%{txt}%"],
            ["User", "name", "like", f"%{txt}%"],
        ]

    return frappe.get_all(
        "User",
        filters=filters,
        or_filters=or_filters,
        fields=["name", "full_name", "user_image"],
        order_by="full_name asc",
        limit_page_length=MAX_MENTIONABLE,
    )


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

COMMENT_FIELDS = ["name", "content", "owner", "creation", "modified"]


@frappe.whitelist()
def get_comments(doctype, name):
    _ensure_app_access()
    _check_reference(doctype, name)

    comments = frappe.get_all(
        "Comment",
        filters={
            "comment_type": "Comment",
            "reference_doctype": doctype,
            "reference_name": name,
        },
        fields=COMMENT_FIELDS,
        order_by="creation asc",
        limit_page_length=0,
    )
    _attach_users(comments)
    return {"comments": comments, "current_user": frappe.session.user}


@frappe.whitelist(methods=["POST"])
def add_comment(doctype, name, content):
    """Read permission is enough to comment.

    Someone who can see a task should be able to ask a question about it;
    requiring write would silence exactly the stakeholders a sign-off needs.
    """
    _ensure_app_access()
    _check_reference(doctype, name)

    # Mentions come off the raw input; the stored copy is sanitised.
    mentions = extract_mentions(content)
    clean = clean_comment_html(content)
    if not strip_html(clean).strip() and "<img" not in (clean or "").lower():
        frappe.throw(_("Comment cannot be empty"))

    doc = frappe.get_doc(
        {
            "doctype": "Comment",
            "comment_type": "Comment",
            "reference_doctype": doctype,
            "reference_name": name,
            "content": clean,
            "comment_email": frappe.session.user,
            "comment_by": get_fullname(frappe.session.user),
        }
    )
    # The reference document's permission is the real gate and was checked
    # above; the Comment doctype itself carries no useful permission rules.
    doc.insert(ignore_permissions=True)

    payload = {
        "name": doc.name,
        "content": doc.content,
        "owner": doc.owner,
        "creation": doc.creation,
        "modified": doc.modified,
    }
    rows = [payload]
    _attach_users(rows)

    _notify_mentions(doctype, name, clean, mentions)
    _publish_comment(doctype, name, rows[0])
    return {"comment": rows[0]}


@frappe.whitelist(methods=["POST"])
def delete_comment(comment):
    _ensure_app_access()
    row = frappe.db.get_value(
        "Comment",
        comment,
        ["owner", "comment_type", "reference_doctype", "reference_name"],
        as_dict=True,
    )
    if not row or row.comment_type != "Comment":
        frappe.throw(_("Comment not found"), frappe.DoesNotExistError)

    _check_reference(row.reference_doctype, row.reference_name)
    if row.owner != frappe.session.user and not _is_manager():
        frappe.throw(_("You can only delete your own comments"), frappe.PermissionError)

    frappe.delete_doc("Comment", comment, ignore_permissions=True)
    return {"deleted": comment}


def _notify_mentions(doctype, name, content, mentions):
    if not mentions:
        return
    sender = frappe.session.user
    recipients = []
    for user in mentions:
        if user == sender:
            continue
        if not frappe.db.exists("User", {"name": user, "enabled": 1}):
            continue
        # Never notify someone into a document they cannot open — the subject
        # alone would leak its content.
        if not frappe.has_permission(doctype, ptype="read", doc=name, user=user):
            continue
        recipients.append(user)
    if not recipients:
        return

    enqueue_create_notification(
        recipients,
        {
            "type": "Mention",
            "document_type": doctype,
            "document_name": name,
            "subject": _("{0} mentioned you in {1}").format(
                get_fullname(sender), _reference_title(doctype, name)
            ),
            "from_user": sender,
            "email_content": content,
        },
    )


def _publish_comment(doctype, name, comment):
    """Push into the document's room so an open thread appends live.

    Published from here rather than a `Comment` doc_event: a doc_event on
    Comment would fire for every Like, Edit and Info comment site-wide to do
    nothing. The trade-off is that a comment written in Desk does not push —
    it still appears on the next fetch.
    """
    try:
        frappe.publish_realtime(
            "agile_comment",
            {"doctype": doctype, "name": name, "comment": comment},
            doctype=doctype,
            docname=name,
            after_commit=True,
        )
    except Exception:
        # Realtime is a nicety; never fail a write because the socket is down.
        frappe.log_error(title="agile_projects: comment publish failed")


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_assignees(doctype, name):
    _ensure_app_access()
    _check_reference(doctype, name)
    return {"assignees": _assignee_list(frappe.db.get_value(doctype, name, "_assign"))}


def _assignee_list(raw):
    """Decode the `_assign` JSON blob into resolved users."""
    try:
        users = json.loads(raw or "[]")
    except (ValueError, TypeError):
        users = []
    rows = [{"user": user} for user in users if user]
    _attach_users(rows, key="user")
    return rows


def attach_assignees(rows):
    """Batched `_assign` decoding for list payloads (board cards, list views).

    One User query for the whole page rather than one per row.
    """
    everyone = set()
    decoded = []
    for row in rows:
        try:
            users = json.loads(row.get("_assign") or "[]")
        except (ValueError, TypeError):
            users = []
        users = [u for u in users if u]
        decoded.append(users)
        everyone.update(users)

    lookup = {}
    if everyone:
        lookup = {
            u.name: u
            for u in frappe.get_all(
                "User",
                filters={"name": ["in", list(everyone)]},
                fields=["name", "full_name", "user_image"],
            )
        }

    for row, users in zip(rows, decoded):
        row["assignees"] = [
            {
                "user": user,
                "user_name": lookup[user].full_name if user in lookup else user,
                "user_image": lookup[user].user_image if user in lookup else None,
            }
            for user in users
        ]
        # The raw blob is an implementation detail; don't ship it to the client.
        row.pop("_assign", None)


@frappe.whitelist(methods=["POST"])
def assign_task(task, users):
    _ensure_app_access()
    _check_reference("Task", task, ptype="write")

    users = frappe.parse_json(users) or []
    if isinstance(users, str):
        users = [users]

    existing = {row["user"] for row in _assignee_list(frappe.db.get_value("Task", task, "_assign"))}
    subject = _reference_title("Task", task)
    skipped = []
    to_add = []
    for user in users:
        if not user or user in existing:
            continue
        if not frappe.db.exists("User", {"name": user, "enabled": 1}):
            skipped.append(user)
            continue
        # Same rule as mentions: assignment notifies, and a notification into a
        # document someone cannot open is both useless and a leak.
        if not frappe.has_permission("Task", ptype="read", doc=task, user=user):
            skipped.append(user)
            continue
        to_add.append(user)

    if to_add:
        assign_to.add(
            {
                "doctype": "Task",
                "name": task,
                "assign_to": to_add,
                "description": subject,
                "assigned_by": frappe.session.user,
            }
        )

    return {
        "assignees": _assignee_list(frappe.db.get_value("Task", task, "_assign")),
        "skipped": skipped,
    }


@frappe.whitelist(methods=["POST"])
def unassign_task(task, user):
    _ensure_app_access()
    _check_reference("Task", task, ptype="write")
    assign_to.remove("Task", task, user)
    return {"assignees": _assignee_list(frappe.db.get_value("Task", task, "_assign"))}


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_attachments(doctype, name):
    _ensure_app_access()
    _check_reference(doctype, name)
    files = frappe.get_all(
        "File",
        filters={"attached_to_doctype": doctype, "attached_to_name": name},
        fields=["name", "file_name", "file_url", "file_size", "is_private", "owner", "creation"],
        order_by="creation desc",
        limit_page_length=0,
    )
    _attach_users(files)
    return {"files": files}


@frappe.whitelist(methods=["POST"])
def delete_attachment(file):
    _ensure_app_access()
    row = frappe.db.get_value(
        "File", file, ["attached_to_doctype", "attached_to_name", "owner"], as_dict=True
    )
    if not row:
        frappe.throw(_("File not found"), frappe.DoesNotExistError)

    # Permission the document it hangs off, not just the File row.
    _check_reference(row.attached_to_doctype, row.attached_to_name, ptype="write")
    if row.owner != frappe.session.user and not _is_manager():
        frappe.throw(_("You can only remove files you uploaded"), frappe.PermissionError)

    # Ownership and the parent document's write permission were both checked
    # above; the File doctype's own if_owner rule would refuse a manager
    # tidying up someone else's upload, which is precisely who may.
    frappe.delete_doc("File", file, ignore_permissions=True)
    return {"deleted": file}


# ---------------------------------------------------------------------------
# Activity timeline
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_activity(doctype, name, limit=50):
    """Field changes and comments as one chronological story."""
    _ensure_app_access()
    _check_reference(doctype, name)
    limit = min(cint(limit) or 50, 200)

    entries = []
    for version in frappe.get_all(
        "Version",
        filters={"ref_doctype": doctype, "docname": name},
        fields=["name", "owner", "creation", "data"],
        order_by="creation desc",
        limit_page_length=limit,
    ):
        lines = describe_version(version.data)
        if not lines:
            continue
        entries.append(
            {
                "kind": "change",
                "name": version.name,
                "owner": version.owner,
                "creation": version.creation,
                "lines": lines,
            }
        )

    for comment in frappe.get_all(
        "Comment",
        filters={
            "comment_type": "Comment",
            "reference_doctype": doctype,
            "reference_name": name,
        },
        fields=COMMENT_FIELDS,
        order_by="creation desc",
        limit_page_length=limit,
    ):
        entries.append(
            {
                "kind": "comment",
                "name": comment.name,
                "owner": comment.owner,
                "creation": comment.creation,
                "content": comment.content,
            }
        )

    entries.sort(key=lambda entry: str(entry["creation"]), reverse=True)
    entries = entries[:limit]
    _attach_users(entries)
    return {"entries": entries}


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_notifications(limit=20):
    _ensure_app_access()
    user = frappe.session.user
    rows = frappe.get_all(
        "Notification Log",
        filters={"for_user": user},
        fields=[
            "name",
            "subject",
            "type",
            "document_type",
            "document_name",
            "from_user",
            "read",
            "creation",
        ],
        order_by="creation desc",
        limit_page_length=min(cint(limit) or 20, 50),
    )
    _attach_deep_links(rows)
    _attach_users(rows, key="from_user")
    return {
        "notifications": rows,
        "unread": frappe.db.count("Notification Log", {"for_user": user, "read": 0}),
    }


def _attach_deep_links(rows):
    """Resolve SPA routes in bulk — one project lookup per doctype, not per row.

    A notification whose document is not something the SPA can show (or was
    since deleted) simply gets no link rather than a dead one.
    """
    wanted = {}
    for row in rows:
        doctype = row.get("document_type")
        if doctype in COMMENTABLE and doctype != "Project" and row.get("document_name"):
            wanted.setdefault(doctype, set()).add(row["document_name"])

    projects = {}
    for doctype, names in wanted.items():
        for found in frappe.get_all(
            doctype, filters={"name": ["in", list(names)]}, fields=["name", "project"]
        ):
            projects[(doctype, found.name)] = found.project

    for row in rows:
        doctype, name = row.get("document_type"), row.get("document_name")
        if doctype not in COMMENTABLE or not name:
            row["link"] = None
            continue
        row["link"] = _spa_link(doctype, name, project=projects.get((doctype, name)))


@frappe.whitelist(methods=["POST"])
def mark_notification_read(notification):
    _ensure_app_access()
    owner = frappe.db.get_value("Notification Log", notification, "for_user")
    if owner != frappe.session.user:
        frappe.throw(_("Not your notification"), frappe.PermissionError)
    frappe.db.set_value("Notification Log", notification, "read", 1, update_modified=False)
    return {"unread": frappe.db.count("Notification Log", {"for_user": frappe.session.user, "read": 0})}


@frappe.whitelist(methods=["POST"])
def mark_all_notifications_read():
    _ensure_app_access()
    frappe.db.set_value(
        "Notification Log",
        {"for_user": frappe.session.user, "read": 0},
        "read",
        1,
        update_modified=False,
    )
    return {"unread": 0}
