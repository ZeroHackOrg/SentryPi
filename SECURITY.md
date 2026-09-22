# 🔒 Security Policy

SentryPi is engineered to demonstrate **security-at-the-compilation-level**.
This policy covers responsible disclosure, the supported security surface, and
the threat model for this repository.

## Supported Versions

| Version | Supported |
| :--- | :--- |
| 0.2.x | ✅ Maintained |
| 0.1.x | ⚠️ Critical issues only |

## Reporting a Vulnerability

Please do **not** open a public GitHub issue for security-related findings.

**Private reporting:**

- Email: [security@zerohack.org](mailto:security@zerohack.org)
- Include: affected version, a minimal `.pi` / CLI reproduction, expected vs.
  actual behavior, and (if known) the subsystem affected (`lexer`, `parser`,
  `static_analyzer`, `crypto`, `target_arm`, `compiler`, `cli`, `playground`).

We acknowledge valid reports and aim to ship a fix in the next release. Please
allow a private disclosure window before publicizing details.

## Scope (attack surface)

This repository is a **compile-time** tool: it does not ship a runtime that
listens on a network. The primary attack surface is **hostile source input**:

- Malformed / oversized `.pi` files (lexical bounds, panic-mode recovery paths).
- Signature-forging or tampering against the HMAC-SHA256 gate (`crypto.py`).
- Local code execution against the web playground (`sentryc serve`) — never
  exposed beyond localhost without containerization.
- Output artifacts (`_driver.py`, `.sh`) are generated code compiled from
  **verified, firewall-cleared** sources; `FORCE OVERRIDE` is never synthesized.

## In-Scope Defensive Guarantees

1. **Compile-time firewall** — no unsafe source produces a binary.
2. **Cryptographic integrity** — unsigned or tampered source is rejected before
   compilation when a key is configured.
3. **No runtime attack surface** — deployed devices run deterministic scripts
   with no interpreter-driven network exposure.
4. **Deterministic codegen** — optimizer barriers prevent unsafe write folding
   across branches and `DELAY`.

## Out of Scope

Physical-attacker capabilities beyond the GPIO user-space device model, custom
kernel drivers, and side-channel resistance are the subject of ZeroHack Custom
Integration engagements, not the open-source core.

## Enterprise Support

Commercial deployments (SLA engineering support, compliance documentation,
custom backends) are handled by **ZeroHack Labs**:
[solutions@zerohack.org](mailto:solutions@zerohack.org).

For the confidentiality, ownership, and licensed-delivery strategy behind the
open-core model, see [docs/ENTERPRISE-DELIVERY.md](docs/ENTERPRISE-DELIVERY.md).