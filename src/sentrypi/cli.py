import argparse
import os
import sys

from . import VERSION
from .compiler import compile_file
from .crypto import configured_key, sign_payload, extract_authenticate
from .lexer import LexError


def _report(message):
    print(message)

def build_parser():
    parser = argparse.ArgumentParser(
        prog="sentryc",
        description="SentryPi security-first DSL compiler for Raspberry Pi IoT.",
        epilog="Example: sentryc examples/alarm.pi",
    )
    parser.add_argument("source", help="path to the .pi source file")
    parser.add_argument(
        "-o",
        "--output-dir",
        default=".",
        help="directory for emitted artifacts (default: current directory)",
    )
    parser.add_argument(
        "--no-bin",
        action="store_true",
        help="skip writing the hardened .bin execution mapping",
    )
    parser.add_argument(
        "--no-map",
        action="store_true",
        help="skip writing the human-readable .map listing",
    )
    parser.add_argument(
        "--no-sh",
        action="store_true",
        help="skip synthesizing the deployable sysfs bash script",
    )
    parser.add_argument(
        "--no-driver",
        action="store_true",
        help="skip synthesizing the high-speed /dev/gpiomem driver",
    )
    parser.add_argument(
        "--hard",
        action="store_true",
        help="enterprise strict mode: escalate TOCTOU, overload & loop-bound warnings "
        "and threat signatures to errors",
    )
    parser.add_argument(
        "--key",
        default=None,
        help="master signing key (hex or passphrase); overrides SENTRYPI_MASTER_KEY env",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"sentryc {VERSION} (SentryPi Security Compiler)",
    )
    return parser


def _handle_compile(argv):
    args = build_parser().parse_args(argv)
    master = args.key if args.key is not None else os.environ.get("SENTRYPI_MASTER_KEY")
    result = compile_file(
        args.source,
        output_dir=args.output_dir,
        emit_bin=not args.no_bin,
        emit_map=not args.no_map,
        emit_sh=not args.no_sh,
        emit_driver=not args.no_driver,
        master_key=master,
        hard=args.hard,
        report=_report,
    )
    if result.crypto_error:
        return 2
    if result.syntax_errors:
        for error in result.syntax_errors:
            print(f"SYNTAX ERROR [Line {error.line}]: {error.message}")
        plural = "s" if len(result.syntax_errors) != 1 else ""
        print(f"Compilation aborted. {len(result.syntax_errors)} syntax error{plural} discovered (panic-mode recovery).")
        return 1
    if not result.ok:
        return 2
    return 0


def _handle_audit(argv):
    parser = argparse.ArgumentParser(
        prog="sentryc audit",
        description="Run a security audit: firewall, threat signatures, and CVE registry.",
    )
    parser.add_argument("source", nargs="?", help="path to the .pi source file")
    parser.add_argument(
        "--key",
        default=None,
        help="master signing key (hex or passphrase); overrides SENTRYPI_MASTER_KEY env",
    )
    parser.add_argument(
        "--hard",
        action="store_true",
        help="enterprise strict mode: escalate warnings to errors (fail closed)",
    )
    parser.add_argument(
        "--registry",
        action="store_true",
        help="print the CVE pattern registry instead of auditing a source file",
    )
    args = parser.parse_args(argv)

    if args.registry:
        from .threats import registry_summary

        print("SentryPi CVE pattern registry")
        print("-" * 78)
        print(f"{'ID':<22} {'SEVERITY':<9} {'CWE':<16} FAMILY")
        print("-" * 78)
        for entry in registry_summary():
            print(f"{entry['id']:<22} {entry['severity']:<9} {entry['cwe']:<16} {entry['family']}")
        print("-" * 78)
        return 0

    if not args.source:
        parser.error("source is required unless --registry is used")

    master = args.key if args.key is not None else os.environ.get("SENTRYPI_MASTER_KEY")
    result = compile_file(
        args.source,
        output_dir=".",
        emit_bin=False,
        emit_map=False,
        emit_sh=False,
        emit_driver=False,
        emit_ino=False,
        emit_ll=False,
        master_key=master,
        hard=args.hard,
        report=lambda _message: None,
    )
    if result.crypto_error:
        print("SECURITY AUDIT FAILED (integrity): " + result.crypto_error)
        return 2

    findings = list(result.errors) + list(result.warnings)
    if not result.ok and result.syntax_errors:
        for error in result.syntax_errors:
            print(f"SYNTAX [Line {error.line}]: {error.message}")

    print(f"Security audit report for {args.source} (target: {result.target_id})")
    print("-" * 100)
    if not findings and not result.syntax_errors:
        print("No findings. Source is safe for deployment.")
        print("-" * 100)
        return 0

    print(f"{'LINE':<6} {'SEVERITY':<9} {'RULE':<20} MESSAGE")
    print("-" * 100)
    for issue in findings:
        rule = issue.rule or "-"
        print(f"{issue.line:<6} {issue.severity:<9} {rule:<20} {issue.message}")
    for error in result.syntax_errors:
        print(f"{error.line:<6} {'ERROR':<9} {'syntax':<20} {error.message}")
    print("-" * 100)

    if result.crypto_error:
        return 2
    if result.syntax_errors:
        return 1
    if not result.ok:
        return 2
    return 0


def _handle_sign(argv):
    parser = argparse.ArgumentParser(
        prog="sentryc sign",
        description="Attach an HMAC-SHA256 AUTHENTICATE header to a .pi source file.",
    )
    parser.add_argument("source", help="path to the .pi source file")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="output path (default: overwrite source in place)",
    )
    parser.add_argument(
        "--key",
        default=None,
        help="master signing key (hex or passphrase); overrides SENTRYPI_MASTER_KEY env",
    )
    args = parser.parse_args(argv)

    key = configured_key(args.key)
    if key is None:
        print("ERROR: signing requires a master key: pass --key or set SENTRYPI_MASTER_KEY.")
        return 1

    text = open(args.source, encoding="utf-8").read()
    payload, _ = extract_authenticate(text)
    signature = sign_payload(payload, key)
    signed_source = f'AUTHENTICATE WITH "0x{signature}"\n{payload}'

    output = args.output or args.source
    with open(output, "w", encoding="utf-8") as handle:
        handle.write(signed_source)

    print(f"[SentryPi] Signed with HMAC-SHA256: 0x{signature}")
    print(f"[SentryPi] AUTHENTICATE header written to '{output}'.")
    print("[SentryPi] Compile with the same key to verify source integrity.")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        build_parser().print_help()
        return 1
    if argv[0] == "sign":
        try:
            return _handle_sign(argv[1:])
        except FileNotFoundError:
            print("ERROR: source file not found.")
            return 1
    if argv[0] == "serve":
        try:
            from .playground import serve

            serve(argv[1:])
            return 0
        except KeyboardInterrupt:
            print("\n[SentryPi] Playground stopped.")
            return 0

    if argv[0] == "audit":
        try:
            return _handle_audit(argv[1:])
        except FileNotFoundError:
            print("ERROR: source file not found.")
            return 1

    try:
        return _handle_compile(argv)
    except FileNotFoundError:
        print(f"ERROR: source file not found: {argv[0]}")
        return 1
    except LexError as error:
        print(f"Threat Vector Rejected [Line {error.line}]: {error.message}")
        return 1


if __name__ == "__main__":
    sys.exit(main())