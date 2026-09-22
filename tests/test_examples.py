import tempfile
import unittest
from pathlib import Path

from sentrypi.compiler import compile_file

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _compile(name):
    with tempfile.TemporaryDirectory(prefix="sentrypi-ex-") as work:
        return compile_file(
            str(EXAMPLES / name),
            output_dir=work,
            emit_bin=False,
            emit_map=False,
            emit_sh=False,
            emit_driver=False,
        )


class TestStoryExamples(unittest.TestCase):
    def test_living_room_compiles_clean(self):
        result = _compile("living_room.pi")
        self.assertTrue(result.ok)
        self.assertEqual(result.threat_count, 0)
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.syntax_errors), 0)
        self.assertIsNone(result.bin_path)

    def test_device_fault_blocked_by_safe_fail_firewall(self):
        result = _compile("device_fault.pi")
        self.assertFalse(result.ok)
        self.assertGreater(result.threat_count, 0)
        self.assertIsNone(result.bin_path)
        self.assertIsNone(result.sh_path)


if __name__ == "__main__":
    unittest.main()