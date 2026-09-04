"""Pure-function tests for the module gate model.

Everything here is arithmetic and string mapping — no database, no fixtures —
so `bench --site <site> run-tests --app agile_projects` covers the rules that
decide whether a module may advance, and how far along a project is.

The gate rules that need a document (open tasks, previous gate) are exercised
in test_agile_module.py.
"""

import itertools
import unittest

from agile_projects.agile_projects.doctype.agile_module.agile_module import (
    GATE_POSITION,
    GATES,
)
from agile_projects.progress import READINESS_SHARE, TASK_SHARE, blend_progress
from agile_projects.setup.install import derive_gate


class TestGateModel(unittest.TestCase):
    def test_positions_cover_every_gate_and_only_rise(self):
        self.assertEqual(set(GATE_POSITION), set(GATES))
        positions = [GATE_POSITION[gate] for gate in GATES]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual((positions[0], positions[-1]), (0.0, 1.0))


class TestDeriveGate(unittest.TestCase):
    """The checklist -> modules migration ladder.

    Conservative by construction: it derives the furthest gate the legacy row
    can actually evidence, and never derives Live.
    """

    def test_nothing_recorded_lands_at_configure(self):
        self.assertEqual(derive_gate({}), "Configure")

    def test_work_in_progress_does_not_advance_a_gate(self):
        self.assertEqual(derive_gate({"configuration_status": "In Progress"}), "Configure")
        self.assertEqual(
            derive_gate(
                {"configuration_status": "Configured", "data_migration_status": "In Progress"}
            ),
            "Migrate",
        )

    def test_configured_reaches_migrate(self):
        for status in ("Configured", "Verified"):
            self.assertEqual(derive_gate({"configuration_status": status}), "Migrate")

    def test_migrated_reaches_uat(self):
        for status in ("Migrated", "Validated"):
            self.assertEqual(derive_gate({"data_migration_status": status}), "UAT")

    def test_signoff_reaches_signoff_regardless_of_the_rest(self):
        self.assertEqual(
            derive_gate({"functional_signoff": 1, "configuration_status": "Not Started"}),
            "Sign-off",
        )

    def test_never_derives_live(self):
        """Going live is a human assertion the old data cannot prove."""
        for signoff, config, migration in itertools.product(
            [0, 1, "0", "1"],
            ["Not Started", "In Progress", "Configured", "Verified", None],
            ["Not Started", "In Progress", "Migrated", "Validated", None],
        ):
            gate = derive_gate(
                {
                    "functional_signoff": signoff,
                    "configuration_status": config,
                    "data_migration_status": migration,
                }
            )
            self.assertIn(gate, GATES)
            self.assertNotEqual(gate, "Live")


class TestBlendProgress(unittest.TestCase):
    def test_shares_sum_to_one(self):
        self.assertAlmostEqual(TASK_SHARE + READINESS_SHARE, 1.0)

    def test_nothing_to_measure_scores_zero(self):
        self.assertEqual(blend_progress(None, None), 0)

    def test_a_missing_side_renormalises_rather_than_dragging_the_score_down(self):
        self.assertEqual(blend_progress(80, None), 80)
        self.assertEqual(blend_progress(None, 50), 50)

    def test_blend(self):
        # every task done, every module in UAT
        self.assertAlmostEqual(blend_progress(100, 50), 85.0)
        self.assertAlmostEqual(blend_progress(100, 100), 100.0)

    def test_gate_movement_alone_moves_the_project(self):
        """The point of the change: gate position replaced a binary sign-off,
        so a module reaching UAT shows up even with no task activity."""
        at_configure = blend_progress(50, GATE_POSITION["Configure"] * 100)
        at_uat = blend_progress(50, GATE_POSITION["UAT"] * 100)
        at_live = blend_progress(50, GATE_POSITION["Live"] * 100)
        self.assertLess(at_configure, at_uat)
        self.assertLess(at_uat, at_live)
        self.assertAlmostEqual(at_live - at_configure, READINESS_SHARE * 100)
