import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sentrypi.compiler import compile_text
from sentrypi.crypto import extract_authenticate, sign_payload
from sentrypi.target_arm import MAGIC, PHYSICAL_TO_BCM, emit_map


class TestCompiler(unittest.TestCase):
    def test_compile_alarm(self):
        source = (
            "LINK PIN 18 TO TARGET_LED AS OUTPUT\n"
            "LINK PIN 23 TO MOTION_SENSOR AS INPUT\n"
            "ATOMIC\n"
            "    IF MOTION_SENSOR IS HIGH THEN\n"
            "        TRIGGER TARGET_LED HIGH\n"
            "        LOG \"Alert.\"\n"
            "    END\n"
            "END\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = compile_text(source, output_dir=tmp, name="alarm")
            self.assertTrue(result.ok)
            self.assertEqual(result.threat_count, 0)
            self.assertEqual(result.removed_count, 0)
            self.assertTrue(result.bin_path.endswith("alarm.bin"))
            self.assertTrue(result.map_path.endswith("alarm.map"))
            self.assertTrue(result.sh_path.endswith("alarm.sh"))
            self.assertTrue(result.driver_path.endswith("alarm_driver.py"))
            with open(result.bin_path, "rb") as handle:
                self.assertEqual(handle.read(4), MAGIC)
            with open(result.map_path) as handle:
                self.assertIn("BRANCH", handle.read())
            with open(result.sh_path) as handle:
                self.assertIn("#!/bin/bash", handle.read())
            with open(result.driver_path) as handle:
                driver_source = handle.read()
                self.assertIn("/dev/gpiomem", driver_source)
                self.assertIn("read_pin(", driver_source)

    def test_compile_blocked_payload(self):
        source = "LINK PIN 02 TO SYSTEM_CLOCK\nFORCE OVERRIDE BUFFER WITH \"A\" * 5000\n"
        with tempfile.TemporaryDirectory() as tmp:
            result = compile_text(source, output_dir=tmp, name="attack")
            self.assertFalse(result.ok)
            self.assertEqual(result.threat_count, 2)
            self.assertIsNone(result.bin_path)
            self.assertIsNone(result.map_path)
            self.assertIsNone(result.sh_path)

    def test_compile_optimized(self):
        source = (
            "LINK PIN 18 TO ALARM AS OUTPUT\n"
            "ALARM HIGH\n"
            "ALARM HIGH\n"
            "ALARM LOW\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = compile_text(source, output_dir=tmp, name="opt")
            self.assertTrue(result.ok)
            self.assertEqual(result.removed_count, 1)

    def test_emit_map_contents(self):
        source = "LINK PIN 18 TO TARGET_LED AS OUTPUT\nTRIGGER TARGET_LED HIGH\nLOG \"done\"\n"
        program = __import__("sentrypi.parser", fromlist=["Parser"]).Parser(
            __import__("sentrypi.lexer", fromlist=["tokenize"]).tokenize(source)
        ).parse_program()
        listing = emit_map(
            __import__("sentrypi.ir", fromlist=["IRGenerator"]).IRGenerator().generate(program)
        )
        self.assertIn("[0] LINK", listing)
        self.assertIn("[1] TRIGGER", listing)
        self.assertIn("done", listing)

    def test_delay_appears_in_map_and_bash(self):
        source = "LINK PIN 18 TO LED AS OUTPUT\nLED HIGH\nDELAY 500 MS\nLED LOW\n"
        with tempfile.TemporaryDirectory() as tmp:
            result = compile_text(source, output_dir=tmp, name="blink")
            self.assertTrue(result.ok)
            with open(result.map_path) as handle:
                self.assertIn("value=500ms", handle.read())
            with open(result.sh_path) as handle:
                self.assertIn("sleep 0.500", handle.read())
            with open(result.driver_path) as handle:
                self.assertIn("time.sleep(0.500)", handle.read())

    def test_hard_mode_rejects_toctou(self):
        source = "LINK PIN 23 TO PIR AS INPUT\nLINK PIN 18 TO A AS OUTPUT\nIF PIR HIGH THEN\n    A HIGH\nEND\n"
        with tempfile.TemporaryDirectory() as tmp:
            relaxed = compile_text(source, output_dir=tmp, name="race")
            self.assertTrue(relaxed.ok)
            self.assertGreaterEqual(len(relaxed.warnings), 1)
            strict = compile_text(source, output_dir=tmp, name="race", hard=True)
            self.assertFalse(strict.ok)
            self.assertEqual(strict.threat_count, 1)

    def test_hard_mode_rejects_overload(self):
        source = "LINK PIN 18 TO LED AS OUTPUT\n" + "LED HIGH\nLED LOW\n" * 13
        with tempfile.TemporaryDirectory() as tmp:
            relaxed = compile_text(source, output_dir=tmp, name="strobe")
            self.assertTrue(relaxed.ok)
            strict = compile_text(source, output_dir=tmp, name="strobe", hard=True)
            self.assertFalse(strict.ok)
            self.assertEqual(strict.threat_count, 1)

    def test_sign_then_compile_verifies(self):
        payload = "LINK PIN 18 TO LED AS OUTPUT\nLED HIGH\n"
        signed = f'AUTHENTICATE WITH "0x{sign_payload(payload, b"master-key")}"\n{payload}'
        with tempfile.TemporaryDirectory() as tmp:
            result = compile_text(
                signed, output_dir=tmp, name="signed", master_key="master-key"
            )
            self.assertTrue(result.ok)
            self.assertIsNone(result.crypto_error)

    def test_tampered_source_rejected(self):
        payload = "LINK PIN 18 TO LED AS OUTPUT\nLED HIGH\n"
        signed = f'AUTHENTICATE WITH "0x{sign_payload(payload, b"master-key")}"\n{payload}'
        tampered = signed.replace("LED HIGH", "LED LOW")
        with tempfile.TemporaryDirectory() as tmp:
            result = compile_text(
                tampered, output_dir=tmp, name="tampered", master_key="master-key"
            )
            self.assertFalse(result.ok)
            self.assertIsNotNone(result.crypto_error)
            self.assertIsNone(result.bin_path)

    def test_unsigned_source_rejected_with_key(self):
        source = "LINK PIN 18 TO LED AS OUTPUT\nLED HIGH\n"
        with tempfile.TemporaryDirectory() as tmp:
            result = compile_text(source, output_dir=tmp, name="unsigned", master_key="secret")
            self.assertFalse(result.ok)
            self.assertIsNotNone(result.crypto_error)

    def test_unsigned_source_ok_without_key(self):
        source = "LINK PIN 18 TO LED AS OUTPUT\nLED HIGH\n"
        with tempfile.TemporaryDirectory() as tmp:
            result = compile_text(source, output_dir=tmp, name="dev")
            self.assertTrue(result.ok)
            self.assertIsNone(result.crypto_error)

    def test_smart_home_kit_compiles_clean(self):
        source = (
            "LINK PIN 18 TO LIVING_LIGHT AS OUTPUT\n"
            "LINK PIN 22 TO GARAGE_LIGHT AS OUTPUT\n"
            "LINK PIN 23 TO MOTION AS INPUT\n"
            "LINK PIN 24 TO DOOR_SENSOR AS INPUT\n"
            "TRIGGER LIVING_LIGHT LOW\n"
            "DELAY 250 MS\n"
            "ATOMIC\n"
            "    IF MOTION HIGH THEN\n"
            "        TRIGGER LIVING_LIGHT HIGH\n"
            "    END\n"
            "END\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = compile_text(source, output_dir=tmp, name="smarthome")
            self.assertTrue(result.ok)
            self.assertEqual(result.threat_count, 0)
            self.assertTrue(result.driver_path.endswith("smarthome_driver.py"))
            with open(result.map_path) as handle:
                listing = handle.read()
                self.assertIn("value=250ms", listing)
                self.assertIn("BRANCH", listing)
            with open(result.driver_path) as handle:
                self.assertIn("write_pin(24, 0)", handle.read())

    def test_physical_to_bcm_mapping(self):
        self.assertEqual(PHYSICAL_TO_BCM[18], 24)
        self.assertEqual(PHYSICAL_TO_BCM[23], 11)


if __name__ == "__main__":
    unittest.main()