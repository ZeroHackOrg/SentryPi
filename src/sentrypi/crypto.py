import hmac
import hashlib
import os
import re

_LANG_HEADER = re.compile(r'AUTHENTICATE\s+WITH\s+"((?:0x)?[0-9a-fA-F]{16,128})"\s*')
_SIG_HEADER = re.compile(r"#\s*AUTH_SIG:\s*((?:0x)?[0-9a-fA-F]{16,128})\s*")

_ENV_KEY = "SENTRYPI_MASTER_KEY"


class SecurityException(Exception):
    pass


def parse_key(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    hex_part = value[2:] if value.startswith(("0x", "0X")) else value
    if re.fullmatch(r"[0-9a-fA-F]+", hex_part) and len(hex_part) % 2 == 0:
        try:
            return bytes.fromhex(hex_part)
        except ValueError:
            pass
    return value.encode("utf-8")


def configured_key(explicit=None):
    if explicit is not None:
        return parse_key(explicit)
    return parse_key(os.environ.get(_ENV_KEY, None))


def _normalize(signature):
    return signature[2:] if signature.startswith(("0x", "0X")) else signature


def extract_authenticate(source):
    lines = source.split("\n")
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index >= len(lines):
        return source, None
    header = lines[index].strip()
    match = _LANG_HEADER.match(header) or _SIG_HEADER.match(header)
    if not match:
        return source, None
    payload = "\n".join(lines[index + 1 :])
    return payload, _normalize(match.group(1))


def sign_payload(payload, secret_key):
    return hmac.new(secret_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


class CryptoSignatureVerifier:
    def __init__(self, secret_key):
        self.secret_key = secret_key

    def verify(self, source):
        payload, provided = extract_authenticate(source)
        if provided is None:
            raise SecurityException(
                "COMPILE BLOCKED: Unsigned Source Code. SentryPi compiler requires "
                "verified developer cryptographic signatures (AUTHENTICATE WITH \"0x…\")."
            )
        expected = sign_payload(payload, self.secret_key)
        if not hmac.compare_digest(provided.lower(), expected.lower()):
            raise SecurityException(
                "CRITICAL: Signature Mismatch! Firmware modification or "
                "script injection attempt intercepted by ZeroHack Firewall."
            )
        return True