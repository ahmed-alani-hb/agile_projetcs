"""Cross-file consistency guards.

These assert agreements that no single file can enforce and that a unit test of
any one module would never notice. Each one is here because it has actually
gone wrong, or came within one edit of going wrong, during development.
"""

import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def read(*parts):
    return (ROOT.joinpath(*parts)).read_text()


class TestViewTypesAgree(unittest.TestCase):
    """The list of view types lives in four places.

    Adding a view means touching all four, and missing one fails in a different
    way each time: the server rejects a saved view, the router silently falls
    back to the board, or the switcher simply has no button.
    """

    def views_py(self):
        block = re.search(r"VIEW_TYPES = \((.*?)\)", read("agile_projects", "views.py"), re.S)
        return set(re.findall(r'"([\w]+)"', block.group(1)))

    def router_js(self):
        block = re.search(
            r"VIEW_TYPES = \[(.*?)\]", read("frontend", "src", "router.js"), re.S
        )
        return set(re.findall(r"'([\w]+)'", block.group(1)))

    def switcher(self):
        source = read("frontend", "src", "components", "ViewSwitcher.vue")
        return set(re.findall(r"value: '([\w]+)'", source))

    def saved_view_doctype(self):
        path = ROOT / "agile_projects/agile_projects/doctype/agile_saved_view/agile_saved_view.json"
        doc = json.loads(path.read_text())
        field = next(f for f in doc["fields"] if f["fieldname"] == "view_type")
        return set(field["options"].split("\n"))

    def test_all_four_definitions_match(self):
        server = self.views_py()
        self.assertTrue(server, "could not parse VIEW_TYPES from views.py")
        self.assertEqual(server, self.router_js(), "router.js disagrees with views.py")
        self.assertEqual(server, self.switcher(), "ViewSwitcher.vue disagrees with views.py")
        self.assertEqual(
            server, self.saved_view_doctype(), "Agile Saved View options disagree with views.py"
        )


class TestEndpointsResolve(unittest.TestCase):
    """Every endpoint the SPA calls must exist and be whitelisted.

    A typo here is a 404 at runtime in whichever view nobody opened yet.
    """

    def whitelisted(self):
        import ast

        found = set()
        for path in (ROOT / "agile_projects").rglob("*.py"):
            dotted = str(path.relative_to(ROOT).with_suffix("")).replace("/", ".")
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.FunctionDef) and any(
                    "whitelist" in ast.unparse(d) for d in node.decorator_list
                ):
                    found.add(f"{dotted}.{node.name}")
        return found

    def test_every_spa_url_is_a_whitelisted_function(self):
        available = self.whitelisted()
        self.assertTrue(available)
        missing = []
        source_root = ROOT / "frontend" / "src"
        for path in list(source_root.rglob("*.vue")) + list(source_root.rglob("*.js")):
            for match in re.finditer(r"url:\s*'(agile_projects\.[^']+)'", path.read_text()):
                if match.group(1) not in available:
                    missing.append(f"{match.group(1)} ({path.name})")
        self.assertEqual(missing, [], "SPA calls endpoints that do not exist")


class TestChartPaletteProvenance(unittest.TestCase):
    """The chart palette was chosen by a validator, not by eye.

    Its separation margins are the reason the flow chart is readable for
    colourblind users; a well-meaning "let's match the board colours" edit
    would silently undo that, so the shape is pinned here.
    """

    def test_flow_palette_is_the_validated_one(self):
        source = read("frontend", "src", "utils", "charts.js")
        self.assertIn(
            "export const FLOW_COLORS = ['#a5b4fc', '#6366f1', '#312e81', '#dc2626']", source
        )

    def test_four_bands_not_six(self):
        # Six adjacent fills cannot be separated by a single-hue ramp; the
        # collapse to four is what makes the palette pass.
        source = read("frontend", "src", "utils", "charts.js")
        bands = re.findall(r"\{ key: '(\w+)'", source)
        self.assertEqual(bands, ["not_started", "in_progress", "done", "blocked"])
