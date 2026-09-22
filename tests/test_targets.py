import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sentrypi import targets as target_registry
from sentrypi.targets import DEFAULT_TARGET, TARGETS, Target, get, register


class TestTargetRegistry(unittest.TestCase):
    def test_arm_is_registered_by_default(self):
        self.assertIn("arm", TARGETS)
        self.assertEqual(DEFAULT_TARGET, "arm")

    def test_get_default_target(self):
        target = get()
        self.assertEqual(target.id, "arm")
        self.assertIn("Raspberry Pi 4B", target.boards)

    def test_get_registered_target_by_id(self):
        self.assertEqual(get("arm").id, "arm")

    def test_get_unknown_target_raises(self):
        with self.assertRaises(KeyError):
            get("atari-2600")

    def test_env_selects_target(self):
        old = os.environ.pop("SENTRYPI_TARGET", None)
        try:
            os.environ["SENTRYPI_TARGET"] = "arm"
            self.assertEqual(get().id, "arm")
        finally:
            os.environ.pop("SENTRYPI_TARGET", None)
            if old is not None:
                os.environ["SENTRYPI_TARGET"] = old

    def test_register_requires_target_instance(self):
        with self.assertRaises(TypeError):
            register("not-a-target")

    def test_register_custom_target(self):
        dummy = Target(
            id="dummy-fpga",
            name="Dummy FPGA",
            boards=("TestBench",),
            emit=lambda tac: b"",
            emits_sh=False,
        )
        register(dummy)
        try:
            self.assertEqual(get("dummy-fpga").id, "dummy-fpga")
            self.assertFalse(get("dummy-fpga").emits_sh)
        finally:
            TARGETS.pop("dummy-fpga", None)

    def test_registered_target_capability_flags(self):
        target = get("arm")
        self.assertTrue(target.emits_bin)
        self.assertTrue(target.emits_map)
        self.assertTrue(target.emits_sh)
        self.assertTrue(target.emits_driver)
        self.assertIn("physical_to_bcm", target.metadata)


if __name__ == "__main__":
    unittest.main()