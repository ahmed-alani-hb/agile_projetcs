"""Pure-function tests for the collaboration layer.

`extract_mentions` decides who gets notified, so it is worth pinning against
the exact HTML frappe-ui's TextEditor emits:
`<span class="mention" data-type="mention" data-id="…">@Label</span>`
(frappe-ui/src/components/TextEditor/extensions/mention/mention-extension.ts).

No database, no fixtures — runs under
`bench --site <site> run-tests --app agile_projects`.
"""

import unittest

from agile_projects.collaboration import (
    COMMENTABLE,
    clean_comment_html,
    describe_version,
    extract_mentions,
)


def mention(user, label="Someone"):
    return f'<span class="mention" data-type="mention" data-id="{user}" data-label="{label}">@{label}</span>'


class TestExtractMentions(unittest.TestCase):
    def test_nothing_to_find(self):
        for html in ("", None, "<p>plain comment</p>", "<p>email me at a@b.com</p>"):
            self.assertEqual(extract_mentions(html), [])

    def test_single_mention(self):
        html = f"<p>{mention('ahmed@example.com', 'Ahmed')} can you look?</p>"
        self.assertEqual(extract_mentions(html), ["ahmed@example.com"])

    def test_order_is_preserved_and_duplicates_collapse(self):
        html = (
            f"<p>{mention('b@x.com')} and {mention('a@x.com')} "
            f"and {mention('b@x.com')} again</p>"
        )
        self.assertEqual(extract_mentions(html), ["b@x.com", "a@x.com"])

    def test_matches_on_data_type_alone(self):
        # Class names are a styling decision; the data-type is the contract.
        html = '<span data-type="mention" data-id="c@x.com">@C</span>'
        self.assertEqual(extract_mentions(html), ["c@x.com"])

    def test_matches_on_class_alone(self):
        html = '<span class="mention" data-id="d@x.com">@D</span>'
        self.assertEqual(extract_mentions(html), ["d@x.com"])

    def test_ignores_a_span_that_merely_has_a_data_id(self):
        html = '<span data-id="not-a-user">text</span>'
        self.assertEqual(extract_mentions(html), [])

    def test_ignores_a_lookalike_class(self):
        html = '<span class="mentioned-elsewhere" data-id="e@x.com">x</span>'
        self.assertEqual(extract_mentions(html), [])

    def test_single_quoted_attributes(self):
        html = "<span data-type='mention' data-id='f@x.com'>@F</span>"
        self.assertEqual(extract_mentions(html), ["f@x.com"])

    def test_extra_attributes_and_whitespace(self):
        html = '<span  style="color:red"  data-type = "mention"  data-id = "g@x.com" >@G</span>'
        self.assertEqual(extract_mentions(html), ["g@x.com"])


class TestDescribeVersion(unittest.TestCase):
    def test_handles_junk_without_raising(self):
        for data in (None, "", "not json", "[]", "{}", 42):
            self.assertEqual(describe_version(data), [])

    def test_field_change(self):
        data = '{"changed": [["status", "To Do", "In Progress"]]}'
        self.assertEqual(describe_version(data), ["changed status from To Do to In Progress"])

    def test_accepts_a_dict_as_well_as_a_string(self):
        self.assertEqual(
            describe_version({"changed": [["priority", "Low", "High"]]}),
            ["changed priority from Low to High"],
        )

    def test_set_and_cleared(self):
        self.assertEqual(
            describe_version('{"changed": [["exp_end_date", null, "2026-09-30"]]}'),
            ["set due date to 2026-09-30"],
        )
        self.assertEqual(
            describe_version('{"changed": [["exp_end_date", "2026-09-30", ""]]}'),
            ["cleared due date"],
        )

    def test_check_fields_read_as_ticked(self):
        self.assertEqual(
            describe_version('{"changed": [["functional_signoff", 0, 1]]}'),
            ["ticked functional sign-off"],
        )

    def test_bookkeeping_and_ordering_churn_is_dropped(self):
        data = """{"changed": [
            ["modified", "a", "b"],
            ["board_order", 1, 2],
            ["_assign", "[]", "[\\"x\\"]"],
            ["gate_order", 0, 3]
        ]}"""
        self.assertEqual(describe_version(data), [])

    def test_a_no_op_change_is_dropped(self):
        self.assertEqual(describe_version('{"changed": [["status", "Done", "Done"]]}'), [])

    def test_unknown_field_is_humanised_rather_than_skipped(self):
        self.assertEqual(
            describe_version('{"changed": [["custom_thing", "a", "b"]]}'),
            ["changed custom thing from a to b"],
        )

    def test_long_values_are_truncated(self):
        long = "x" * 200
        line = describe_version(f'{{"changed": [["subject", "old", "{long}"]]}}')[0]
        self.assertLess(len(line), 120)
        self.assertTrue(line.endswith("…"))

    def test_child_rows_are_summarised_not_enumerated(self):
        data = """{"added": [["depends_on", {}], ["depends_on", {}]],
                   "removed": [["depends_on", {}]]}"""
        lines = describe_version(data)
        self.assertIn("added 2 dependency rows", lines)
        self.assertIn("removed 1 dependency row", lines)

    def test_malformed_change_rows_are_skipped(self):
        self.assertEqual(describe_version('{"changed": [["status"], null, 5]}'), [])


class TestCleanCommentHtml(unittest.TestCase):
    """Comment bodies are rendered with v-html, so this is the XSS boundary."""

    def assertStripped(self, raw, *needles):
        cleaned = clean_comment_html(raw).lower()
        for needle in needles:
            self.assertNotIn(needle, cleaned, f"{needle!r} survived in {cleaned!r}")

    def test_script_tag_and_its_body_go(self):
        self.assertStripped("<p>hi</p><script>alert(1)</script>", "<script", "alert(1)")

    def test_unclosed_script_tag_goes(self):
        self.assertStripped("<p>hi</p><script src=evil.js>", "<script")

    def test_json_shaped_body_is_still_sanitised(self):
        # frappe.utils.sanitize_html returns JSON untouched by default; this is
        # the short-circuit clean_comment_html exists to close.
        self.assertStripped('{"x": "<script>alert(1)</script>"}', "<script", "alert(1)")

    def test_iframe_object_embed_and_form_go(self):
        self.assertStripped(
            "<iframe src=x></iframe><object></object><embed><form></form>",
            "<iframe",
            "<object",
            "<embed",
            "<form",
        )

    def test_style_blocks_go(self):
        self.assertStripped("<style>body{display:none}</style><p>hi</p>", "<style")

    def test_ordinary_formatting_survives(self):
        cleaned = clean_comment_html("<p>Please <strong>check</strong> the <em>data</em>.</p>")
        self.assertIn("<strong>", cleaned)
        self.assertIn("<em>", cleaned)
        self.assertIn("check", cleaned)

    def test_mention_markup_survives_so_the_thread_still_reads_right(self):
        raw = '<p><span class="mention" data-type="mention" data-id="a@b.com">@A</span> look</p>'
        self.assertIn("data-id", clean_comment_html(raw))

    def test_empty_and_none(self):
        self.assertEqual(clean_comment_html(None), "")
        self.assertEqual(clean_comment_html(""), "")


class TestCommentableAllowlist(unittest.TestCase):
    def test_covers_what_the_spa_links_to_and_nothing_else(self):
        self.assertEqual(
            set(COMMENTABLE), {"Task", "Agile Module", "Cutover Step", "Project"}
        )
        for risky in ("User", "File", "Comment", "Notification Log", "System Settings"):
            self.assertNotIn(risky, COMMENTABLE)


class TestMentionWiring(unittest.TestCase):
    """Guards for a bug unit tests could not otherwise reach.

    Typing @ showed nobody for two independent reasons, and both live at
    integration seams rather than inside a function:

    1. frappe-ui's TextEditor builds its extensions once in onMounted and never
       watches the `mentions` prop, so a plain array is snapshotted — empty, for
       an async list. Only the object-with-getter form survives to the
       extension's per-keystroke `toValue()`.
    2. Mentions were sourced from Employee, whose `user_id` link is optional and
       routinely blank, so the list could be empty regardless.

    These assert the shape of the fix rather than its behaviour, because the
    behaviour lives in the browser.
    """

    def spa_file(self, name):
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[2]
        return (root / "frontend" / "src" / "components" / name).read_text()

    def test_the_mention_prop_keeps_its_getter_form(self):
        source = self.spa_file("CommentThread.vue")
        self.assertIn("mentions: () =>", source)
        # Check the markup only: the script's comment names the broken form on
        # purpose, as a warning, and must not trip this guard.
        template = source.split("</template>")[0]
        self.assertIn(':mentions="mentionConfig"', template)
        self.assertNotIn(':mentions="mentionOptions"', template)

    def test_mentions_and_assignment_draw_from_users_not_employees(self):
        for name in ("CommentThread.vue", "AssigneePicker.vue"):
            source = self.spa_file(name)
            self.assertIn("collaboration.get_mentionable_users", source, name)
            self.assertNotIn("api.get_employees", source, name)

    def test_sme_picker_still_uses_employees(self):
        # SME Responsible is a genuine Link -> Employee and must stay one.
        self.assertIn("api.get_employees", self.spa_file("EmployeePicker.vue"))
