"""Network-layer threat signatures and the CVE pattern registry.

SentryPi's DSL is deterministic by construction, so the remaining attack
surface lives in the *payload data* a program embeds (LOG strings, FORCE
OVERRIDE values, craftable identifiers). ``scan_threats`` sweeps the raw
source text for network-layer threat signatures (raw sockets, port binding,
cleartext retransmission) and for known vulnerability patterns catalogued in
the CVE registry below.

The registry is self-managed: each entry maps to a CWE family and a
verifiable description, and is versioned with a SentryPi-internal ID so the
set can grow without claiming false positives on vendor-specific advisories.
"""

import re

from .static_analyzer import SecurityIssue

RULE_NETWORK_THREAT = "network_threat"
RULE_CVE_SIGNATURE = "cve_signature"

# Network-layer threat signatures. Each is (rule, label, pattern, message).
# Matches are reported at WARN severity and escalate to ERROR in --hard mode,
# so a network-threat payload can never ship to a production gate.
NET_THREAT_PATTERNS = [
    (
        RULE_NETWORK_THREAT,
        "raw-socket",
        r"socket\s*\(|SOCK_RAW",
        "Network threat: raw-socket primitive detected; raw sockets bypass the "
        "kernel TCP/IP stack and can spoof traffic.",
    ),
    (
        RULE_NETWORK_THREAT,
        "port-bind",
        r"\bbind\s*\(|\bsetsockopt\s*\(",
        "Network threat: port-binding primitive detected; an uncontrolled port "
        "bind exposes an inbound listener.",
    ),
    (
        RULE_NETWORK_THREAT,
        "wildcard-bind",
        r"0\.0\.0\.0",
        "Network threat: wildcard bind address detected; the service listens on "
        "every interface instead of a controlled one.",
    ),
    (
        RULE_NETWORK_THREAT,
        "packet-recv",
        r"\brecvfrom\s*\(|\brecv\s*\(",
        "Network threat: unbounded packet receive primitive detected; oversized "
        "datagrams can overflow the receive staging buffer.",
    ),
    (
        RULE_NETWORK_THREAT,
        "packet-send",
        r"\bsendto\s*\(|\bsend\s*\(",
        "Network threat: raw packet transmit primitive detected; traffic escapes "
        "the application firewall envelope.",
    ),
    (
        RULE_NETWORK_THREAT,
        "port-exposure",
        r"\bport\s+[0-9]{1,5}\b",
        "Network threat: explicit port number embedded in payload; associate "
        "listeners with an authorized network policy instead.",
    ),
    (
        RULE_NETWORK_THREAT,
        "address-family",
        r"\bAF_INET\b|\bAF_PACKET\b",
        "Network threat: raw address-family literal detected; forces low-level "
        "network stack access.",
    ),
]

# CVE pattern registry (self-managed, CWE-aligned).
CVE_REGISTRY = [
    {
        "id": "SENTRY-CVE-2026-001",
        "family": "Unsafe string copy",
        "cwe": "CWE-121 / CWE-676",
        "severity": "HIGH",
        "pattern": r"\bstrcpy\s*\(|\bstrcat\s*\(|\bsprintf\s*\(|\bgets\s*\(",
        "description": "Fixed-size stack buffers written with unbounded copy "
        "primitives permit stack or heap overwrite.",
        "references": "CWE-121 Stack-based Buffer Overflow; CWE-676 Use of Potentially "
        "Dangerous Function",
    },
    {
        "id": "SENTRY-CVE-2026-002",
        "family": "Unbounded receive",
        "cwe": "CWE-120 / CWE-190",
        "severity": "HIGH",
        "pattern": r"\brecvfrom\s*\([^)]*,\s*[^,]+,\s*[^,]+\)|\bmemcpy\s*\(.*sizeof",
        "description": "Receive kernels that do not length-check incoming data can "
        "overflow the destination staging buffer.",
        "references": "CWE-120 Buffer Copy without Checking Size of Input; CWE-190 "
        "Integer Overflow or Wraparound",
    },
    {
        "id": "SENTRY-CVE-2026-003",
        "family": "Hard-coded credential",
        "cwe": "CWE-798",
        "severity": "HIGH",
        "pattern": r"\b(password|passwd|pwd|api[_-]?key|secret)\s*[:=]\s*\\?[\"']?[\w\-]+\\?[\"']?",
        "description": "Embedded static credentials survive firmware extraction and "
        "grant permanent access to persisted devices.",
        "references": "CWE-798 Use of Hard-coded Credentials; OWASP IoT Top 10 I9",
    },
    {
        "id": "SENTRY-CVE-2026-004",
        "family": "Shell command injection",
        "cwe": "CWE-78",
        "severity": "CRITICAL",
        "pattern": r"\bsystem\s*\(|\bpopen\s*\(|\bsubprocess\s*|exec\w*\(|os\.system",
        "description": "Dispatching fragments to a shell lets crafted input escalate "
        "to arbitrary command execution on the device.",
        "references": "CWE-78 Improper Neutralization of Special Elements used in an OS "
        "Command; OWASP Command Injection",
    },
    {
        "id": "SENTRY-CVE-2026-005",
        "family": "Disabled transport security",
        "cwe": "CWE-319 / CWE-295",
        "severity": "HIGH",
        "pattern": r"http://|ssl_verify\s*=\s*(false|0)|verify_certs?\s*=\s*(false|0)|CERT_NONE",
        "description": "Downgraded or unverified transports expose telemetry and "
        "command traffic to on-path interception.",
        "references": "CWE-319 Cleartext Transmission; CWE-295 Improper Certificate "
        "Verification; RFC 8446 TLS 1.3",
    },
    {
        "id": "SENTRY-CVE-2026-006",
        "family": "Manual memory ownership",
        "cwe": "CWE-122",
        "severity": "MEDIUM",
        "pattern": r"\bmalloc\s*\(|\bfree\s*\(|\brealloc\s*\(|new\s+[A-Za-z_]+\[\s*[0-9]+",
        "description": "Hand-managed heap ownership in firmware is a standing source "
        "of use-after-free and double-free defects.",
        "references": "CWE-122 Heap-based Buffer Overflow; CWE-416 Use After Free",
    },
]

_COMPILED_NET = [
    (label, re.compile(pattern, re.IGNORECASE), message)
    for _, label, pattern, message in NET_THREAT_PATTERNS
]
_COMPILED_CVE = [
    (entry["id"], re.compile(entry["pattern"], re.IGNORECASE), entry) for entry in CVE_REGISTRY
]


def scan_threats(source_text):
    """Scan raw source for network and CVE-pattern threats.

    Returns a list of ``SecurityIssue`` (WARN severity by default). Under
    ``--hard`` the caller escalates these like any firewall warning.
    """
    issues = []
    lines = source_text.splitlines()
    for line_number, line in enumerate(lines, start=1):
        for label, pattern, message in _COMPILED_NET:
            if pattern.search(line):
                issues.append(
                    SecurityIssue("WARN", line_number, message, RULE_NETWORK_THREAT)
                )
        for cve_id, pattern, entry in _COMPILED_CVE:
            if pattern.search(line):
                issues.append(
                    SecurityIssue(
                        "WARN",
                        line_number,
                        f"CVE signature {cve_id} ({entry['family']}, {entry['cwe']}): "
                        f"{entry['description']}",
                        RULE_CVE_SIGNATURE,
                    )
                )
    return issues


def registry_summary():
    """Return the CVE registry as a list of dicts for reporting/CLI use."""
    return [
        {
            "id": entry["id"],
            "family": entry["family"],
            "cwe": entry["cwe"],
            "severity": entry["severity"],
        }
        for entry in CVE_REGISTRY
    ]