import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sentrypi.compiler import compile_text
from sentrypi.threats import (
    CVE_REGISTRY,
    RULE_CVE_SIGNATURE,
    RULE_NETWORK_THREAT,
    registry_summary,
    scan_threats,
)


class TestThreatScan(unittest.TestCase):
    def test_raw_socket_detected(self):
        issues = scan_threats('LOG "payload socket(AF_INET, SOCK_RAW)"')
        self.assertTrue(
            any(issue.rule == RULE_NETWORK_THREAT and "raw-socket" in issue.message for issue in issues)
        )

    def test_port_bind_detected(self):
        issues = scan_threats('LOG "bind(0.0.0.0)"')
        self.assertTrue(any("port-bind" in issue.message for issue in issues))
        self.assertTrue(any("wildcard" in issue.message for issue in issues))

    def test_hard_coded_credential_cve(self):
        issues = scan_threats('LOG "password = hunter2"')
        self.assertTrue(any(issue.rule == RULE_CVE_SIGNATURE for issue in issues))
        self.assertTrue(any("SENTRY-CVE-2026-003" in issue.message for issue in issues))

    def test_escaped_credential_detected(self):
        issues = scan_threats('LOG "password = \\"hunter2\\""')
        self.assertTrue(any("SENTRY-CVE-2026-003" in issue.message for issue in issues))

    def test_clean_source_has_no_findings(self):
        source = (
            "LINK PIN 18 TO LED AS OUTPUT\n"
            "LED HIGH\n"
            'LOG "system nominal"\n'
        )
        self.assertEqual(scan_threats(source), [])

    def test_registry_is_versioned(self):
        self.assertGreaterEqual(len(CVE_REGISTRY), 4)
        for entry in CVE_REGISTRY:
            self.assertTrue(entry["id"])
            self.assertTrue(entry["cwe"])
            self.assertTrue(entry["pattern"])
        summary = registry_summary()
        self.assertEqual(len(summary), len(CVE_REGISTRY))
        self.assertIn("severity", summary[0])


class TestThreatIntegration(unittest.TestCase):
    def test_relaxed_compile_warns_and_passes(self):
        source = (
            "LINK PIN 18 TO LED AS OUTPUT\n"
            "LED HIGH\n"
            'LOG "socket(AF_INET, SOCK_RAW) bind(0.0.0.0) port 4444"\n'
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = compile_text(source, output_dir=tmp, name="pad")
            self.assertTrue(result.ok)
            self.assertGreaterEqual(len(result.threats), 1)
            self.assertGreaterEqual(len(result.warnings), 1)

    def test_hard_mode_fails_closed(self):
        source = (
            "LINK PIN 18 TO LED AS OUTPUT\n"
            'LOG "socket(AF_INET, SOCK_RAW) bind(0.0.0.0)"\n'
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = compile_text(source, output_dir=tmp, name="bad", hard=True)
            self.assertFalse(result.ok)
            self.assertGreaterEqual(result.threat_count, 1)
            self.assertIsNone(result.bin_path)


if __name__ == "__main__":
    unittest.main()