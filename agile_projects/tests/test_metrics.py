"""Pure-function tests for the metrics helpers.

No database. These cover the arithmetic the dashboards rest on, and in
particular the two places where a plausible-looking implementation would be
quietly wrong: an unestimated task must weigh 1 point rather than 0, and an
empty dataset must yield None rather than 0.
"""

import unittest
from datetime import date

from agile_projects.metrics import (
    bucket_by_week,
    gate_history_from_versions,
    lead_time_days,
    percentile,
    points_of,
    summarise_counts,
    velocity_from_completions,
    week_start,
)


class TestPointsOf(unittest.TestCase):
    """complexity_points is a Select of strings, so this is not just int()."""

    def test_parses_the_string_values_the_field_actually_holds(self):
        for raw, expected in [("1", 1), ("3", 3), ("13", 13)]:
            self.assertEqual(points_of({"complexity_points": raw}), expected)

    def test_unestimated_weighs_one_not_zero(self):
        # A project of entirely unestimated tasks must still show progress.
        for raw in (None, "", 0, "0"):
            self.assertEqual(points_of({"complexity_points": raw}), 1)
        self.assertEqual(points_of({}), 1)


class TestPercentile(unittest.TestCase):
    def test_no_data_is_none_not_zero(self):
        # "nobody has finished anything" and "everything took zero days" are
        # different answers; a tile must not conflate them.
        self.assertIsNone(percentile([], 0.5))
        self.assertIsNone(percentile([None, None], 0.5))

    def test_single_value(self):
        self.assertEqual(percentile([7], 0.5), 7)
        self.assertEqual(percentile([7], 0.95), 7)

    def test_median_and_interpolation(self):
        self.assertEqual(percentile([1, 2, 3], 0.5), 2)
        self.assertEqual(percentile([1, 2, 3, 4], 0.5), 2.5)
        self.assertEqual(percentile([10, 20], 0.5), 15)

    def test_bounds_are_clamped(self):
        self.assertEqual(percentile([1, 2, 3], 0), 1)
        self.assertEqual(percentile([1, 2, 3], 1), 3)
        self.assertEqual(percentile([1, 2, 3], -5), 1)
        self.assertEqual(percentile([1, 2, 3], 5), 3)

    def test_input_need_not_be_sorted(self):
        self.assertEqual(percentile([3, 1, 2], 0.5), 2)


class TestWeekBucketing(unittest.TestCase):
    def test_week_start_is_monday(self):
        # 2026-09-04 is a Friday.
        self.assertEqual(str(week_start("2026-09-04")), "2026-08-31")
        self.assertEqual(str(week_start("2026-08-31")), "2026-08-31")
        self.assertEqual(str(week_start("2026-09-06")), "2026-08-31")
        self.assertEqual(str(week_start("2026-09-07")), "2026-09-07")

    def test_counts_rows_per_week(self):
        rows = [
            {"d": "2026-08-31"},
            {"d": "2026-09-02"},
            {"d": "2026-09-07"},
        ]
        series = bucket_by_week(rows, "d", since="2026-08-31", until="2026-09-07")
        self.assertEqual(
            series,
            [{"week": "2026-08-31", "value": 2.0}, {"week": "2026-09-07", "value": 1.0}],
        )

    def test_empty_weeks_are_emitted_across_a_month_boundary(self):
        # A gap silently skipped reads as though nothing was ever missed.
        series = bucket_by_week(
            [{"d": "2026-08-24"}, {"d": "2026-09-14"}],
            "d",
            since="2026-08-24",
            until="2026-09-14",
        )
        self.assertEqual([s["week"] for s in series],
                         ["2026-08-24", "2026-08-31", "2026-09-07", "2026-09-14"])
        self.assertEqual([s["value"] for s in series], [1.0, 0.0, 0.0, 1.0])

    def test_weighting(self):
        rows = [{"d": "2026-09-01", "p": "5"}, {"d": "2026-09-02", "p": None}]
        series = bucket_by_week(rows, "d", weight=points_of_p, since="2026-08-31",
                                until="2026-08-31")
        self.assertEqual(series, [{"week": "2026-08-31", "value": 6.0}])

    def test_rows_without_a_date_are_skipped(self):
        self.assertEqual(bucket_by_week([{"d": None}], "d"), [])

    def test_no_rows_and_no_range_is_empty(self):
        self.assertEqual(bucket_by_week([], "d"), [])


def points_of_p(row):
    return points_of({"complexity_points": row.get("p")})


class TestLeadTime(unittest.TestCase):
    def test_whole_days(self):
        self.assertEqual(lead_time_days("2026-09-01", "2026-09-11"), 10)

    def test_same_day_is_zero_not_one(self):
        self.assertEqual(lead_time_days("2026-09-01", "2026-09-01"), 0)

    def test_missing_either_end_is_none(self):
        self.assertIsNone(lead_time_days(None, "2026-09-01"))
        self.assertIsNone(lead_time_days("2026-09-01", None))

    def test_never_negative(self):
        # Clock skew or a hand-edited completed_on must not produce -3 days.
        self.assertEqual(lead_time_days("2026-09-10", "2026-09-01"), 0)


class TestVelocity(unittest.TestCase):
    def test_points_completed_per_week(self):
        tasks = [
            {"completed_on": "2026-08-31", "complexity_points": "5"},
            {"completed_on": "2026-09-01", "complexity_points": "3"},
            {"completed_on": "2026-09-08", "complexity_points": None},
        ]
        # The window ends on a real date, as _window() supplies it — passing a
        # week-start here would clip the final partial week.
        series = velocity_from_completions(tasks, date(2026, 8, 31), date(2026, 9, 8))
        self.assertEqual([s["value"] for s in series], [8.0, 1.0])

    def test_ignores_unfinished_and_out_of_window(self):
        tasks = [
            {"completed_on": None, "complexity_points": "8"},
            {"completed_on": "2020-01-01", "complexity_points": "8"},
        ]
        series = velocity_from_completions(tasks, date(2026, 8, 31), date(2026, 9, 4))
        self.assertEqual(series, [{"week": "2026-08-31", "value": 0.0}])


class TestGateHistory(unittest.TestCase):
    def make(self, changed, docname="MOD-1", creation="2026-09-01 10:00:00"):
        import json
        return {"docname": docname, "creation": creation,
                "data": json.dumps({"changed": changed})}

    def test_extracts_gate_moves(self):
        moves = gate_history_from_versions([
            self.make([["gate", "Configure", "Migrate"]]),
        ])
        self.assertEqual(moves, [{"on": "2026-09-01", "module": "MOD-1",
                                  "from": "Configure", "to": "Migrate"}])

    def test_ignores_other_fields(self):
        self.assertEqual(
            gate_history_from_versions([self.make([["notes", "a", "b"]])]), []
        )

    def test_ignores_unknown_gates_rather_than_guessing(self):
        self.assertEqual(
            gate_history_from_versions([self.make([["gate", "Configure", "Nonsense"]])]), []
        )

    def test_ignores_a_no_op(self):
        self.assertEqual(
            gate_history_from_versions([self.make([["gate", "UAT", "UAT"]])]), []
        )

    def test_survives_junk(self):
        for payload in ({"data": None}, {"data": "not json"}, {"data": "[]"},
                        {"data": '{"changed": [["gate"]]}'}):
            payload.setdefault("docname", "M")
            payload.setdefault("creation", "2026-09-01 10:00:00")
            self.assertEqual(gate_history_from_versions([payload]), [])

    def test_sorted_oldest_first(self):
        moves = gate_history_from_versions([
            self.make([["gate", "UAT", "Sign-off"]], creation="2026-09-05 10:00:00"),
            self.make([["gate", "Configure", "Migrate"]], creation="2026-09-01 10:00:00"),
        ])
        self.assertEqual([m["on"] for m in moves], ["2026-09-01", "2026-09-05"])


class TestSummariseCounts(unittest.TestCase):
    def test_keeps_vocabulary_order_and_zeroes(self):
        rows = [{"s": "b"}, {"s": "b"}, {"s": "a"}]
        self.assertEqual(
            summarise_counts(rows, "s", ["a", "b", "c"]),
            [{"label": "a", "value": 1}, {"label": "b", "value": 2},
             {"label": "c", "value": 0}],
        )

    def test_unknown_values_are_dropped(self):
        result = summarise_counts([{"s": "zzz"}], "s", ["a"])
        self.assertEqual(result, [{"label": "a", "value": 0}])
