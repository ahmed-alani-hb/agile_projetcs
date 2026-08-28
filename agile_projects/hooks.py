app_name = "agile_projects"
app_title = "Agile Projects"
app_publisher = "Honey Bird"
app_description = (
    "Agile project management on ERPNext — standalone Kanban SPA with "
    "complexity points, dependency blocking and ERP module readiness tracking"
)
app_email = "admin@honey-bird.net"
app_license = "mit"

required_apps = ["frappe/erpnext"]

# ---------------------------------------------------------------------------
# Standalone SPA (served at /agile, bypassing Desk entirely)
# ---------------------------------------------------------------------------

website_route_rules = [
    {"from_route": "/agile/<path:app_path>", "to_route": "agile"},
]

add_to_apps_screen = [
    {
        "name": "agile_projects",
        "logo": "/assets/agile_projects/frontend/favicon.svg",
        "title": "Agile Projects",
        "route": "/agile",
        "has_permission": "agile_projects.api.check_app_permission",
    }
]

# ---------------------------------------------------------------------------
# ERPNext extensions
# ---------------------------------------------------------------------------

# Custom Task controller: agile status workflow + strict dependency gate.
override_doctype_class = {
    "Task": "agile_projects.overrides.task.AgileTask",
}

doc_events = {
    "Task": {
        "on_update": "agile_projects.progress.on_task_change",
        "after_delete": "agile_projects.progress.on_task_change",
    },
    "Project": {
        "validate": "agile_projects.progress.on_project_validate",
    },
}

after_install = "agile_projects.setup.install.after_install"
after_migrate = "agile_projects.setup.install.after_migrate"
