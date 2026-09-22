# SentryPi Enterprise Delivery — Confidentiality, Ownership & Product Security

How to protect the value of SentryPi as an enterprise product **without** hiding
behind security theater. Open source means the public repository is cloneable;
real confidentiality comes from licensing, signing, controlled delivery, and
keeping the proprietary surface outside the open repo.

---

## 1. The Fundamental Rule of Open Source

> **A public MIT repo is visible and forkable by design.**
> You cannot make an MIT-licensed codebase private.
> You cannot prevent someone from cloning it.
> Security-by-hiding is not security — it's an invitation to bypass.

SentryPi's strategy therefore does **not** rely on hiding Python source code.
It relies on a layered model where:

1. The **public MIT core** contains no enterprise-only logic.
2. **Enterprise-only value** lives in closed-source licensed components.
3. **All compiled artifacts are signed**, so deployment trust is not rooted in
   source availability.

---

## 2. Open-Core Split Matrix

| Component | Public (MIT) | Proprietary / Licensed |
| :--- | :--- | :--- |
| DSL syntax (`.pi`) |  | — |
| Frontend (lexer, parser, `ATOMIC`, `DELAY`) |  | — |
| Security firewall (TOCTOU, overflow, hijack rules) |  | — |
| IR + optimizer |  | — |
| Raspberry Pi backends (`.bin`, `.map`, `.sh`, `/dev/gpiomem` driver) |  | — |
| HMAC signing (`sentryc sign`) |  | — |
| Web playground (`sentryc serve`) |  | — |
| Unit test suite |  | — |
| ESP32 / STM32 / Arduino backends | — |  Closed, licensed SDK |
| Native ARM register codegen (bare-metal, no Linux) | — |  Closed, licensed SDK |
| Asymmetric signatures (Ed25519 / X.509) | — |  Closed, licensed SDK |
| Custom memory-limit / compliance documentation packs | — |  Closed, licensed SDK |
| AI engine DSL integration | — |  Closed, licensed SDK |
| Per-device key binding / secure boot integration | — |  Bespoke (Custom Integration) |
| SLA support + 24/7 engineering | — |  Enterprise tier |
| Legacy system reverse-engineering | — |  Bespoke (Custom Integration) |

The MIT repo contains **zero** proprietary code. Anyone cloning the repo gets
a fully working compiler — but only the public-core features.

---

## 3. Enterprise Confidentiality & Delivery Controls

### 3.1 Closed-source licensed packaging

Enterprise customers receive:

- A **signed, versioned wheel** or binary bundle (no editable installs) from a
  private package index or artifact server.
- A **checksum manifest** (`SHA256SUMS.txt`) and optional SBOM for supply-chain
  audit (e.g., CycloneDX JSON).
- A **release notice** detailing what changed vs. the open-core version.

Source-available (NDA) can be offered on a case-by-case basis for security-
critical customers; it never replaces the binary delivery.

### 3.2 License enforcement

- The licensed SDK calls `sentrypi.LicenseGate.enforce()` at CLI startup,
  checking a **cryptographically signed license file** bound to the customer's
  machine-id or org domain. License validation is offline-capable (no phone
  home).
- The license file itself is **symmetrically signed** (same pattern as
  `SENTRYPI_MASTER_KEY`) so it cannot be forged without the license authority's
  key.
- The license server / key ceremony stays outside the open repo entirely.

### 3.3 Signed artifact chain (CI → device)

```
source.pi ──sentryc sign──► signed.pi ──compile──► build/
    │                            │                 ├── signed.bin  (hash signed)
    │                            │                 ├── signed.map
    │                            │                 ├── signed.sh
    │                            │                 └── signed_driver.py
    │                            │
    │                            └── device verifiers check source.hash at boot
    │
    └── HMAC key never stored in the repo; held in CI secrets / HSM / KMS
```

- The **HMAC master key** is never committed. In CI it's injected via a secrets
  manager; on physical devices it's provisioned via secure boot / TPM.
- The generated binary (`*.bin`) can carry a hash of the source payload; a
  device-side validator rejects unsigned/unhash-matched firmware.
- The same keying pattern (`sign_payload` / `CryptoSignatureVerifier`) applies
  to runtime MQTT payloads so actuator commands carry end-to-end integrity.

### 3.4 Trademark & ownership

- "SentryPi", "ZeroHack", and the SentryPi logo are **registered/claimed
  trademarks** of ZeroHack.org. Permissive use: fork and study; commercial use
  on product packaging requires explicit license.
- Contributors must sign a **Contributor License Agreement** (CLA) before
  substantial changes merge into `main`, preserving the clear commercial
  boundary.
- Keep the MIT LICENSE file in the repo; do not add additional "non-commercial"
  restrictions that make the repo non-OSI-compliant — those restrictions go
  into the separate commercial license.

### 3.5 Supply chain: what to publish and verify

| Artifact | Publish | Verify before use |
| :--- | :--- | :--- |
| Signed wheel / tarball | `SHA256SUMS.txt` | `sha256sum -c SHA256SUMS.txt` |
| License authority public key | In docs + README | Only trust keys from known ZeroHack channels |
| SBOM (CycloneDX/SPDX) | bundled with release | Audit critical dependencies |
| `_driver.py` / `.bin` | in customer's private repo | Checksum in the customer's SCM + secure boot chain |

---

## 4. Anti-Clone Value That Is Legitimate (no Python obfuscation)

Security through obscurity (bytecode obfuscation, randomized variable names)
is rejected — it frustrates legitimate users and stops no motivated attacker.
The real value extractors that make cloning commercially worthless are:

1. **Licensing** — the enterprise SDK requires a signed license; unauthorized
   use is unlicensed use and legally actionable regardless of source
   availability.
2. **Support & SLA** — customers pay for 24/7 engineering, guaranteed response
   times, and compliance documentation that no fork can replicate.
3. **Compliance packs** — pre-built security documentation, SBOMs, and audit
   evidence for EU CRA, FDA, IEC 62443 are delivered under NDA.
4. **Bespoke backends** — ESP32, STM32, bare-metal ARM, and AI engine packs
   ship as signed, closed-source libraries that never appear in the public
   repo.
5. **Signed, bound, audited artifacts** — a device deployed with a signed
   firmware chain cannot be trivially swapped; the key was never in the
   repository.

> **Bottom line:** build value into the product's edges (signing, licensing,
> backends, documentation, support), not by hiding code in a repo everyone can
> already clone.

---

## 5. What a Clone Gives You (and What It Doesn't)

| An attacker cloning the MIT repo gets: | An attacker **cannot** get: |
| :--- | :--- |
| Full working open-core compiler | Enterprise backends / AI engines |
| All 90+ unit tests | Signed license authority keys |
| RPi 4B/5 backends + playground | Compliance documentation packs |
| HMAC signing (`sentryc sign`) | Asymmetric (Ed25519) signing |
| TOCTOU / overload firewall rules | Bespoke DSL extensions |
| `--hard` strict mode | 24/7 SLA support |
| Copyable `signed.pi` workflow | Per-device binding / secure boot key material |

A clone is a **competent open-source compiler**, not a replacement for the
licensed enterprise product.

---

## 6. Key Don'ts

- **Don't add `non-commercial` clauses to the MIT LICENSE** — use a separate
  commercial license (e.g., a proprietary SDK EULA) instead.
- **Don't obfuscate the public repo** — it frustrates honest users and buys
  you approximately zero security.
- **Don't ship the license-authority key in any release artifact.**
- **Don't confuse security-theater with engineering** — every protection
  documented here is directly testable and verifiable by the customer.