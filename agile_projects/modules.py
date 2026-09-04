"""Module gates and the cutover runbook.

The gate board is a Kanban whose cards are ERP modules rather than tasks, and
whose columns are the delivery gates a module has to earn its way through. The
rules themselves live in the `Agile Module` controller so they hold in Desk
too; everything here is transport.

Conventions match `agile_projects/views.py`: `_ensure_app_access()` first, then
a per-document permission check, and writes are POST-only.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from agile_projects.agile_projects.doctype.agile_module.agile_module import (
    GATE_POSITION,
    GATES,
)
from agile_projects.agile_projects.doctype.cutover_step.cutover_step import (
    STATUSES as CUTOVER_STATUSES,
)
from agile_projects.api import _attach_employee_info, _ensure_app_access
from agile_projects.overrides.task import DONE

MODULE_FIELDS = [
    "name",
    "project",
    "module_name",
    "system_platform",
    "gate",
    "configuration_status",
    "data_migration_status",
    "functional_signoff",
    "sme_responsible",
    "target_go_live",
    "gate_order",
    "notes",
    "modified",
]

MODULE_EDITABLE_FIELDS = {
    "module_name",
    "system_platform",
    "configuration_status",
    "data_migration_status",
    "functional_signoff",
    "sme_responsible",
    "target_go_live",
    "notes",
}

CUTOVER_FIELDS = [
    "name",
    "project",
    "title",
    "description",
    "status",
    "step_order",
    "agile_module",
    "owner_employee",
    "depends_on",
    "planned_start",
    "planned_end",
    "actual_start",
    "actual_end",
    "signed_off_by",
    "signed_off_at",
    "modified",
]

CUTOVER_EDITABLE_FIELDS = {
    "title",
    "description",
    "status",
    "agile_module",
    "owner_employee",
    "depends_on",
    "planned_start",
    "planned_end",
}

BLOCKED = "Blocked"


def _check_project(project, ptype="read"):
    """Project permissions govern everything under a project."""
    if not project:
        frappe.throw(_("A project is required"), frappe.ValidationError)
    frappe.has_permission("Project", ptype=ptype, doc=project, throw=True)


def _module_project(module):
    project = frappe.db.get_value("Agile Module", module, "project")
    if not project:
        frappe.throw(_("Module {0} not found").format(module), frappe.DoesNotExistError)
    return project


def _step_project(step):
    project = frappe.db.get_value("Cutover Step", step, "project")
    if not project:
        frappe.throw(_("Cutover step {0} not found").format(step), frappe.DoesNotExistError)
    return project


def _parse_fields(fields, allowed, label):
    fields = frappe.parse_json(fields) or {}
    invalid = set(fields) - allowed
    if invalid:
        frappe.throw(
            _("Field(s) {0} cannot be updated on {1}").format(", ".join(sorted(invalid)), label)
        )
    return fields


# ---------------------------------------------------------------------------
# Module gate board
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_modules(project):
    """Modules grouped into gate columns, mirroring api.get_board's contract."""
    _ensure_app_access()
    _check_project(project)

    modules = frappe.get_all(
        "Agile Module",
        filters={"project": project},
        fields=MODULE_FIELDS,
        order_by="gate_order asc, modified desc",
        limit_page_length=0,
    )
    _attach_module_task_stats(modules)
    _attach_employee_info(modules)

    columns = {gate: [] for gate in GATES}
    for module in modules:
        # An out-of-options gate (a hand-edited row, a half-finished import)
        # would otherwise vanish from the board entirely.
        gate = module.gate if module.gate in columns else GATES[0]
        columns[gate].append(module)

    return {
        "project": frappe.db.get_value(
            "Project", project, ["name", "project_name", "percent_complete"], as_dict=True
        ),
        "gates": GATES,
        "columns": [{"gate": gate, "modules": columns[gate]} for gate in GATES],
    }


def _attach_module_task_stats(modules):
    """Task rollup per module in one query, not one query per module."""
    for module in modules:
        module["total_tasks"] = 0
        module["done_tasks"] = 0
        module["blocked_tasks"] = 0
        module["task_progress"] = 0

    if not modules:
        return

    by_name = {m.name: m for m in modules}
    tasks = frappe.get_all(
        "Task",
        filters={
            "agile_module": ["in", list(by_name)],
            "is_group": 0,
            "is_template": 0,
        },
        fields=["agile_module", "status", "complexity_points"],
        limit_page_length=0,
    )

    points = {name: {"total": 0, "done": 0} for name in by_name}
    for task in tasks:
        module = by_name.get(task.agile_module)
        if not module:
            continue
        module["total_tasks"] += 1
        if task.status == DONE:
            module["done_tasks"] += 1
        elif task.status == BLOCKED:
            module["blocked_tasks"] += 1
        # Unestimated tasks count as 1 point, matching progress.py.
        weight = cint(task.complexity_points) or 1
        points[task.agile_module]["total"] += weight
        if task.status == DONE:
            points[task.agile_module]["done"] += weight

    for name, module in by_name.items():
        total = points[name]["total"]
        module["task_progress"] = flt(points[name]["done"] / total * 100, 1) if total else 0


@frappe.whitelist(methods=["POST"])
def create_module(
    project,
    module_name,
    system_platform,
    configuration_status=None,
    data_migration_status=None,
    sme_responsible=None,
    target_go_live=None,
):
    _ensure_app_access()
    _check_project(project, ptype="write")

    doc = frappe.get_doc(
        {
            "doctype": "Agile Module",
            "project": project,
            "module_name": module_name,
            "system_platform": system_platform,
            "gate": GATES[0],
            "configuration_status": configuration_status or "Not Started",
            "data_migration_status": data_migration_status or "Not Started",
            "sme_responsible": sme_responsible,
            "target_go_live": target_go_live,
        }
    )
    doc.insert()
    return _module_payload(doc.name, project)


@frappe.whitelist(methods=["POST"])
def update_module(module, fields):
    """Field edits only. A gate move goes through update_module_gate so the
    transition rules are never bypassed by a generic field write."""
    _ensure_app_access()
    project = _module_project(module)
    _check_project(project, ptype="write")

    values = _parse_fields(fields, MODULE_EDITABLE_FIELDS, _("a module"))
    doc = frappe.get_doc("Agile Module", module)
    doc.check_permission("write")
    doc.update(values)
    doc.save()
    return _module_payload(module, project)


@frappe.whitelist(methods=["POST"])
def update_module_gate(module, gate):
    """The enforced transition. A refusal surfaces as GateTransitionError,
    which the SPA shows as a toast before snapping the card back."""
    _ensure_app_access()
    project = _module_project(module)
    _check_project(project, ptype="write")

    if gate not in GATE_POSITION:
        frappe.throw(_("Invalid gate: {0}").format(gate))

    doc = frappe.get_doc("Agile Module", module)
    doc.check_permission("write")
    doc.gate = gate
    doc.save()
    return _module_payload(module, project)


@frappe.whitelist(methods=["POST"])
def delete_module(module):
    _ensure_app_access()
    project = _module_project(module)
    _check_project(project, ptype="write")

    linked = frappe.db.count("Task", {"agile_module": module})
    if linked:
        frappe.throw(
            _("{0} task(s) are still linked to this module. Unlink them first.").format(linked)
        )
    frappe.delete_doc("Agile Module", module)
    return {"percent_complete": frappe.db.get_value("Project", project, "percent_complete")}


@frappe.whitelist(methods=["POST"])
def reorder_gate(project, gate, module_names):
    """Persist card order within a gate column.

    Order only — a cross-column move must go through update_module_gate so the
    transition rules run. Written with db.set_value because reordering is
    high-frequency and must not bump `modified` or re-run validation.
    """
    _ensure_app_access()
    module_names = frappe.parse_json(module_names) or []
    if gate not in GATE_POSITION:
        frappe.throw(_("Invalid gate: {0}").format(gate))
    if not module_names:
        return {"ordered": 0}

    _check_project(project, ptype="read")
    visible = set(
        frappe.get_list(
            "Agile Module",
            filters={"project": project, "name": ["in", module_names]},
            pluck="name",
            limit_page_length=0,
        )
    )
    ordered = 0
    for index, name in enumerate(module_names):
        if name in visible and frappe.has_permission("Agile Module", ptype="write", doc=name):
            frappe.db.set_value("Agile Module", name, "gate_order", index, update_modified=False)
            ordered += 1
    return {"ordered": ordered}


def _module_payload(module, project):
    doc = frappe.get_all(
        "Agile Module", filters={"name": module}, fields=MODULE_FIELDS, limit_page_length=1
    )
    modules = list(doc)
    _attach_module_task_stats(modules)
    _attach_employee_info(modules)
    return {
        "module": modules[0] if modules else None,
        "percent_complete": frappe.db.get_value("Project", project, "percent_complete"),
    }


# ---------------------------------------------------------------------------
# Cutover runbook
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_cutover(project):
    _ensure_app_access()
    _check_project(project)

    steps = frappe.get_all(
        "Cutover Step",
        filters={"project": project},
        fields=CUTOVER_FIELDS,
        order_by="step_order asc, creation asc",
        limit_page_length=0,
    )

    # Resolve the blocker's title and status so the runbook can say *why* a
    # step is not startable without a round-trip per row.
    by_name = {s.name: s for s in steps}
    for step in steps:
        blocker = by_name.get(step.depends_on)
        step["depends_on_title"] = blocker.title if blocker else None
        step["depends_on_status"] = blocker.status if blocker else None

    module_names = {s.agile_module for s in steps if s.get("agile_module")}
    module_labels = {}
    if module_names:
        module_labels = {
            m.name: m.module_name
            for m in frappe.get_all(
                "Agile Module",
                filters={"name": ["in", list(module_names)]},
                fields=["name", "module_name"],
            )
        }
    for step in steps:
        step["module_label"] = module_labels.get(step.get("agile_module"))

    _attach_step_owner_info(steps)
    return {"steps": steps, "statuses": CUTOVER_STATUSES}


def _attach_step_owner_info(steps):
    """`_attach_employee_info` keys off `sme_responsible`; cutover steps name
    the same field `owner_employee`, so map it across and back."""
    for step in steps:
        step["sme_responsible"] = step.get("owner_employee")
    _attach_employee_info(steps)
    for step in steps:
        step.pop("sme_responsible", None)
        step["owner_name"] = step.pop("sme_name", None)
        step["owner_image"] = step.pop("sme_image", None)


@frappe.whitelist(methods=["POST"])
def add_cutover_step(
    project,
    title,
    description=None,
    agile_module=None,
    owner_employee=None,
    depends_on=None,
    planned_start=None,
    planned_end=None,
):
    _ensure_app_access()
    _check_project(project, ptype="write")

    last = frappe.db.get_value(
        "Cutover Step", {"project": project}, "step_order", order_by="step_order desc"
    )
    doc = frappe.get_doc(
        {
            "doctype": "Cutover Step",
            "project": project,
            "title": title,
            "description": description,
            "status": "Pending",
            "step_order": cint(last) + 1,
            "agile_module": agile_module,
            "owner_employee": owner_employee,
            "depends_on": depends_on,
            "planned_start": planned_start,
            "planned_end": planned_end,
        }
    )
    doc.insert()
    return {"step": _step_dict(doc.name)}


@frappe.whitelist(methods=["POST"])
def update_cutover_step(step, fields):
    _ensure_app_access()
    project = _step_project(step)
    _check_project(project, ptype="write")

    values = _parse_fields(fields, CUTOVER_EDITABLE_FIELDS, _("a cutover step"))
    doc = frappe.get_doc("Cutover Step", step)
    doc.check_permission("write")
    doc.update(values)
    doc.save()
    return {"step": _step_dict(step)}


@frappe.whitelist(methods=["POST"])
def start_step(step):
    """Stamps the real start time. Deliberately not gated on `depends_on`: a
    team can prepare a step early — only declaring it done out of order is
    refused, by the controller."""
    _ensure_app_access()
    project = _step_project(step)
    _check_project(project, ptype="write")

    doc = frappe.get_doc("Cutover Step", step)
    doc.check_permission("write")
    doc.status = "In Progress"
    doc.actual_start = doc.actual_start or now_datetime()
    doc.actual_end = None
    doc.save()
    return {"step": _step_dict(step)}


@frappe.whitelist(methods=["POST"])
def complete_step(step, status="Done"):
    _ensure_app_access()
    project = _step_project(step)
    _check_project(project, ptype="write")

    if status not in ("Done", "Skipped", "Failed"):
        frappe.throw(_("Invalid completion status: {0}").format(status))

    doc = frappe.get_doc("Cutover Step", step)
    doc.check_permission("write")
    doc.status = status
    if status != "Failed":
        doc.actual_start = doc.actual_start or now_datetime()
        doc.actual_end = now_datetime()
    doc.save()
    return {"step": _step_dict(step)}


@frappe.whitelist(methods=["POST"])
def signoff_step(step):
    _ensure_app_access()
    project = _step_project(step)
    _check_project(project, ptype="write")

    doc = frappe.get_doc("Cutover Step", step)
    doc.check_permission("write")
    if doc.status != "Done":
        frappe.throw(_("Only a completed step can be signed off."))
    doc.signed_off_by = frappe.session.user
    doc.signed_off_at = now_datetime()
    doc.save()
    return {"step": _step_dict(step)}


@frappe.whitelist(methods=["POST"])
def reorder_cutover(project, step_names):
    _ensure_app_access()
    step_names = frappe.parse_json(step_names) or []
    if not step_names:
        return {"ordered": 0}

    _check_project(project, ptype="read")
    visible = set(
        frappe.get_list(
            "Cutover Step",
            filters={"project": project, "name": ["in", step_names]},
            pluck="name",
            limit_page_length=0,
        )
    )
    ordered = 0
    for index, name in enumerate(step_names):
        if name in visible and frappe.has_permission("Cutover Step", ptype="write", doc=name):
            frappe.db.set_value("Cutover Step", name, "step_order", index, update_modified=False)
            ordered += 1
    return {"ordered": ordered}


@frappe.whitelist(methods=["POST"])
def delete_cutover_step(step):
    _ensure_app_access()
    project = _step_project(step)
    _check_project(project, ptype="write")

    dependents = frappe.get_all("Cutover Step", filters={"depends_on": step}, pluck="title")
    if dependents:
        frappe.throw(
            _("{0} step(s) depend on this one: {1}").format(
                len(dependents), ", ".join(dependents[:5])
            )
        )
    frappe.delete_doc("Cutover Step", step)
    return {"deleted": step}


def _step_dict(step):
    rows = frappe.get_all(
        "Cutover Step", filters={"name": step}, fields=CUTOVER_FIELDS, limit_page_length=1
    )
    steps = list(rows)
    _attach_step_owner_info(steps)
    return steps[0] if steps else None
