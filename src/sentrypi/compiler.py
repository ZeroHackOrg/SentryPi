from dataclasses import dataclass, field
from pathlib import Path

from . import targets as target_registry
from .crypto import CryptoSignatureVerifier, SecurityException, configured_key, extract_authenticate
from .ir import IRGenerator
from .lexer import LexError, tokenize
from .optimizer import optimize
from .parser import Parser
from .semantic_analyzer import SemanticAnalyzer
from .static_analyzer import analyze
from .threats import RULE_CVE_SIGNATURE, RULE_NETWORK_THREAT, scan_threats


@dataclass
class CompileResult:
    ok: bool = False
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    syntax_errors: list = field(default_factory=list)
    crypto_error: str = None
    threats: list = field(default_factory=list)
    target_id: str = "arm"
    bin_path: str = None
    map_path: str = None
    sh_path: str = None
    driver_path: str = None
    ino_path: str = None
    ll_path: str = None
    ir_count: int = 0
    opt_count: int = 0
    removed_count: int = 0

    @property
    def threat_count(self):
        return len(self.errors)


def _no_report(_message):
    return None


def compile_text(
    source_text,
    output_dir=".",
    name="program",
    emit_bin=True,
    emit_map=True,
    emit_sh=True,
    emit_driver=True,
    emit_ino=True,
    emit_ll=True,
    master_key=None,
    hard=False,
    report=_no_report,
):
    result = CompileResult()

    def say(message):
        report(f"[SentryPi] {message}")

    key = configured_key(master_key)
    if key is not None:
        try:
            CryptoSignatureVerifier(key).verify(source_text)
            say("Cryptographic Signature Verification... Verified.")
        except SecurityException as error:
            say("Cryptographic Signature Verification... FAIL.")
            report(f"{error}")
            result.crypto_error = str(error)
            return result
    else:
        _, provided = extract_authenticate(source_text)
        if provided is not None:
            say("Cryptographic Signature Verification... SKIPPED (no SENTRYPI_MASTER_KEY; dev mode).")

    threat_issues = scan_threats(source_text)
    for issue in threat_issues:
        if (
            hard
            and issue.severity == "WARN"
            and issue.rule in (RULE_NETWORK_THREAT, RULE_CVE_SIGNATURE)
        ):
            issue.severity = "ERROR"
    result.threats = threat_issues
    say(f"Scanning threat signatures... {len(threat_issues)} finding(s).")
    for issue in threat_issues:
        report(f"THREAT [Line {issue.line}]: {issue.message}")

    try:
        tokens = tokenize(source_text)
    except LexError as error:
        say("Scanning tokens... FAIL.")
        raise error
    say("Scanning tokens... Success.")

    parser = Parser(tokens)
    program = parser.parse_program()
    if parser.errors:
        say("Building Abstract Syntax Tree... FAIL.")
        result.syntax_errors = list(parser.errors)
        return result
    say("Building Abstract Syntax Tree... Success.")

    semantic_issues = SemanticAnalyzer().analyze(program)
    firewall_issues = analyze(program, hard=hard)
    errors = [
        issue
        for issue in list(firewall_issues)
        + [issue for issue in threat_issues if issue.severity == "ERROR"]
        if issue.severity == "ERROR"
    ]
    warnings = [
        issue
        for issue in list(semantic_issues)
        + [issue for issue in firewall_issues if issue.severity == "WARN"]
        + [issue for issue in threat_issues if issue.severity == "WARN"]
    ]

    say("Running Semantic Analysis... Success.")
    for warning in warnings:
        report(f"WARNING [Line {warning.line}]: {warning.message}")

    if errors:
        say("Running Static Security Firewall...")
        for error in errors:
            report(f"COMPILE ERROR [Line {error.line}]: {error.message}")
        report("Compilation aborted. Physical hardware protected.")
        result.errors = errors
        result.warnings = warnings
        return result

    say(f"Running Static Security Firewall... PASS ({len(errors)} Threats Detected).")

    tac = IRGenerator().generate(program)
    result.ir_count = len(tac)
    tac_optimized, removed = optimize(tac)
    result.opt_count = len(tac_optimized)
    result.removed_count = removed
    say(f"Generating Intermediate Representation... {result.ir_count} TAC instructions.")
    say(
        f"Optimizing instruction schedule... {result.opt_count} instructions "
        f"({result.removed_count} redundant removed)."
    )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    target = target_registry.get()
    result.target_id = target.id
    say(f"Target backend: {target.name} "
        f"(id={target.id}, boards={', '.join(target.boards) or 'unknown'}).")

    if emit_bin and target.emits_bin:
        bin_path = out_dir / f"{name}.bin"
        bin_path.write_bytes(target.emit(tac_optimized))
        result.bin_path = str(bin_path)
        say(f"Emitting hardened execution mapping... Created '{result.bin_path}'")
    if emit_map and target.emits_map:
        map_path = out_dir / f"{name}.map"
        map_path.write_text(target.emit_map(tac_optimized))
        result.map_path = str(map_path)
        say(f"Writing readable map listing... Created '{result.map_path}'")
    if emit_sh and target.emits_sh:
        sh_path = out_dir / f"{name}.sh"
        sh_path.write_text(target.synthesize_bash(program))
        result.sh_path = str(sh_path)
        say(f"Synthesizing deployable sysfs script... Created '{result.sh_path}'")
    if emit_driver and target.emits_driver:
        driver_path = out_dir / f"{name}_driver.py"
        driver_path.write_text(target.synthesize_driver(program))
        result.driver_path = str(driver_path)
        say(f"Synthesizing high-speed /dev/gpiomem driver... Created '{result.driver_path}'")
    if emit_ino and target.emits_ino and target.synthesize_ino:
        ino_path = out_dir / f"{name}.ino"
        ino_path.write_text(target.synthesize_ino(program))
        result.ino_path = str(ino_path)
        say(f"Synthesizing Arduino/ESP32 sketch... Created '{result.ino_path}'")
    if emit_ll and target.emits_ll and target.synthesize_llvm:
        ll_path = out_dir / f"{name}.ll"
        ll_path.write_text(target.synthesize_llvm(program))
        result.ll_path = str(ll_path)
        say(f"Dumping illustrative LLVM-style IR... Created '{result.ll_path}'")

    say("Compilation complete. Safe for deployment.")
    result.ok = True
    result.warnings = warnings
    return result


def compile_file(
    source_path,
    output_dir=".",
    emit_bin=True,
    emit_map=True,
    emit_sh=True,
    emit_driver=True,
    emit_ino=True,
    emit_ll=True,
    master_key=None,
    hard=False,
    report=_no_report,
):
    source = Path(source_path)
    text = source.read_text(encoding="utf-8")
    return compile_text(
        text,
        output_dir=output_dir,
        name=source.stem,
        emit_bin=emit_bin,
        emit_map=emit_map,
        emit_sh=emit_sh,
        emit_driver=emit_driver,
        emit_ino=emit_ino,
        emit_ll=emit_ll,
        master_key=master_key,
        hard=hard,
        report=report,
    )