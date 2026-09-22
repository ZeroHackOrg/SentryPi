# Contributing to SentryPi

Thanks for helping harden the SentryPi compiler. Whether you are fixing a
firewall gap, porting a backend, or improving the docs, this guide keeps the
project consistent and CI-green.

## Setup

```bash
git clone https://github.com/ZeroHackOrg/SentryPi.git
cd sentrypi

python3 -m venv venv
source venv/bin/activate
pip install -e .
```

## Development loop

```bash
python -m unittest discover -s tests -v   # full suite (must stay green)
sentryc examples/alarm.pi                 # CLI smoke test
sentryc examples/race.pi --hard           # firewall strict-mode check
```

## What we look for

- **Security-first changes** touch `lexer`, `parser`, `static_analyzer`,
  `crypto`, or `semantic_analyzer`. Every new rule needs a test that a threat
  is blocked and a healthy equivalent still compiles.
- **Backend changes** to `target_arm.py` must keep all four artifacts
  (`.bin`, `.map`, `.sh`, `_driver.py`) correct — verify with
  `sentryc examples/deploy.pi` and the CI artifact greps.
- **Never weaken a guarantee.** `FORCE OVERRIDE` stays unreachable in output;
  the crypto gate stays in front of tokenization; `--hard` keeps escalating
  TOCTOU/overload to hard errors.
- Match existing style: no type annotations in hot paths unless already used,
  stdlib-only, docstrings only where behavior is non-obvious.

## Committing

- One logical change per commit; reference the rule/feature you touched.
- Run the full test suite before pushing.

## Reporting issues

Open a GitHub issue for bugs and feature requests. For security findings, use
the private channels in [SECURITY.md](SECURITY.md) — do not publish them.

## Roadmap areas open to contributors

See [docs/ARCHITECTURE.md](ARCHITECTURE.md) § 5:
frontend language expansion (`ANALOG_READ`, loops), behavioral firewall rules,
and ESP32 / Arduino / LLVM backend ports.