import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sentrypi.crypto import (
    CryptoSignatureVerifier,
    SecurityException,
    configured_key,
    extract_authenticate,
    parse_key,
    sign_payload,
)


class TestCryptoSignatureVerifier(unittest.TestCase):
    def test_sign_and_verify_roundtrip(self):
        payload = "LINK PIN 18 TO LED AS OUTPUT\nLED HIGH\n"
        signed = f'AUTHENTICATE WITH "0x{sign_payload(payload, b"secret")}"\n{payload}'
        self.assertTrue(CryptoSignatureVerifier(b"secret").verify(signed))

    def test_comment_header_form_is_accepted(self):
        payload = "LINK PIN 18 TO LED AS OUTPUT\n"
        signed = f"# AUTH_SIG: 0x{sign_payload(payload, b"secret")}\n{payload}"
        self.assertTrue(CryptoSignatureVerifier(b"secret").verify(signed))

    def test_unsigned_source_raises(self):
        with self.assertRaises(SecurityException) as ctx:
            CryptoSignatureVerifier(b"secret").verify("LINK PIN 18 TO LED AS OUTPUT\n")
        self.assertIn("Unsigned Source Code", str(ctx.exception))

    def test_tampering_raises_signature_mismatch(self):
        payload = "LINK PIN 18 TO LED AS OUTPUT\nLED HIGH\n"
        signed = f'AUTHENTICATE WITH "0x{sign_payload(payload, b"secret")}"\n{payload}'
        tampered = signed.replace("LED HIGH", "LED LOW")
        with self.assertRaises(SecurityException) as ctx:
            CryptoSignatureVerifier(b"secret").verify(tampered)
        self.assertIn("Signature Mismatch", str(ctx.exception))

    def test_wrong_key_raises(self):
        payload = "LOG \"ping\"\n"
        signed = f'AUTHENTICATE WITH "0x{sign_payload(payload, b"key-a")}"\n{payload}'
        with self.assertRaises(SecurityException):
            CryptoSignatureVerifier(b"key-b").verify(signed)

    def test_payload_strips_only_header(self):
        payload = "LINK PIN 18 TO LED AS OUTPUT\n"
        signed = f'AUTHENTICATE WITH "0x{sign_payload(payload, b"s")}"\n{payload}'
        extracted, _ = extract_authenticate(signed)
        self.assertEqual(extracted, payload)

    def test_extract_returns_none_without_header(self):
        self.assertEqual(extract_authenticate("LINK PIN 18\n")[1], None)

    def test_parse_key_hex_and_passphrase(self):
        self.assertEqual(parse_key("0xdeadbeef"), bytes.fromhex("deadbeef"))
        self.assertEqual(parse_key("00ff"), bytes.fromhex("00ff"))
        self.assertEqual(parse_key("secret"), b"secret")
        env = os.environ.pop("SENTRYPI_MASTER_KEY", None)
        os.environ["SENTRYPI_MASTER_KEY"] = "abcd"
        try:
            self.assertEqual(configured_key(), bytes.fromhex("abcd"))
        finally:
            os.environ.pop("SENTRYPI_MASTER_KEY", None)
            if env is not None:
                os.environ["SENTRYPI_MASTER_KEY"] = env


if __name__ == "__main__":
    unittest.main()