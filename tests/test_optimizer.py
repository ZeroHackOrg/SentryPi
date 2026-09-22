import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sentrypi.optimizer import optimize


class TestOptimizer(unittest.TestCase):
    def test_redundant_write_eliminated(self):
        tac = [
            {"op": "WRITE_BIT", "reg": "t0", "value": 1},
            {"op": "WRITE_BIT", "reg": "t0", "value": 1},
            {"op": "WRITE_BIT", "reg": "t0", "value": 1},
        ]
        optimized, removed = optimize(tac)
        self.assertEqual(len(optimized), 1)
        self.assertEqual(removed, 2)

    def test_consecutive_distinct_writes_kept(self):
        tac = [
            {"op": "WRITE_BIT", "reg": "t0", "value": 1},
            {"op": "WRITE_BIT", "reg": "t0", "value": 0},
            {"op": "WRITE_BIT", "reg": "t0", "value": 1},
        ]
        optimized, removed = optimize(tac)
        self.assertEqual(len(optimized), 3)
        self.assertEqual(removed, 0)

    def test_duplicate_alloc_removed(self):
        tac = [
            {"op": "ALLOC_PIN", "reg": "t0", "pin": 18, "mode": "OUTPUT"},
            {"op": "ALLOC_PIN", "reg": "t0", "pin": 18, "mode": "OUTPUT"},
        ]
        optimized, removed = optimize(tac)
        self.assertEqual(len(optimized), 1)
        self.assertEqual(removed, 1)

    def test_branch_resets_write_folding(self):
        tac = [
            {"op": "WRITE_BIT", "reg": "t0", "value": 1},
            {"op": "BRANCH", "reg": "t1", "value": 1, "label": "L0"},
            {"op": "WRITE_BIT", "reg": "t0", "value": 1},
        ]
        optimized, removed = optimize(tac)
        self.assertEqual(len(optimized), 3)
        self.assertEqual(removed, 0)

    def test_no_op_schedule_untouched(self):
        tac = [{"op": "LABEL", "name": "L0"}]
        optimized, removed = optimize(tac)
        self.assertEqual(optimized, tac)
        self.assertEqual(removed, 0)


if __name__ == "__main__":
    unittest.main()