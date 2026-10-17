"""The Semgrep lane: run the custom rules over the project, and prove each against its fixture.

Semgrep is the Detector for custom Kotlin rules. It is run with its own suppression comments
switched off (`--disable-nosem`), so the only way to cover a finding is a record exception that
names the rule and the file.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kotlin_qa.finding import Finding
from kotlin_qa.rules import Rule, load_rules
from kotlin_qa.suppression import project_files, scope_files, within

if TYPE_CHECKING:
    from kotlin_qa.config import Config
    from kotlin_qa.record import RecordEntry

ERROR = "kqaci.semgrep.error"
UNPROVED = "kqaci.rules.unproved"
STALE = "kqaci.record.stale"
_SOURCE_SUFFIXES = (".kt", ".kts", ".java")
_ARGUMENTS = ("--metrics=off", "--disable-version-check", "--disable-nosem", "--json", "--quiet")


def semgrep_binary() -> str:
    """Return the Semgrep installed beside this interpreter, else the one on PATH."""
    beside = Path(sys.executable).parent / "semgrep"
    if beside.is_file():
        return str(beside)
    return shutil.which("semgrep") or "semgrep"


def _run(rule_files: list[Path], targets: list[str], cwd: Path) -> dict[str, Any] | str:
    """Run Semgrep and return its JSON report, or the reason it could not produce one."""
    command = [semgrep_binary(), *_ARGUMENTS]
    for rule_file in rule_files:
        command.extend(["--config", str(rule_file)])
    with tempfile.TemporaryDirectory(prefix="kotlin-qa-semgrep-") as scratch:
        command.extend(["--output", str(Path(scratch) / "report.json"), *targets])
        try:
            result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
        except OSError as error:
            return f"cannot run semgrep: {error}"
        report = Path(scratch) / "report.json"
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return f"semgrep produced no report (exit {result.returncode}): {result.stderr.strip()}"
    return data if isinstance(data, dict) else "semgrep's report is not an object"


def _identifier(check_id: str, known: set[str]) -> str:
    """Return the rule id Semgrep reported, without the path prefix it adds to a file's rules."""
    if check_id in known:
        return check_id
    return next((i for i in known if check_id.endswith("." + i)), check_id)


def scan_project(
    config: Config, entries: list[RecordEntry], *, paths: tuple[str, ...] | None
) -> list[Finding]:
    """Run every rule over the project, or only paths, and return what the record does not cover.

    A record exception with covers = "findings" covers the findings of one rule in one file. On a
    full scan an exception that covers no finding is reported as stale; a scan of named paths
    cannot tell an unused entry from one for a file outside them.
    """
    rules, _ = load_rules(config)
    if not rules:
        return []
    root = config.root
    names = (
        project_files(root, config.scan_exclude)
        if paths is None
        else scope_files(root, config.scan_exclude, paths)
    )
    # A rule's fixtures hold lines that are meant to fire; the rules lane proves them instead.
    targets = [
        name
        for name in names
        if name.endswith(_SOURCE_SUFFIXES)
        and not any(within(name, directory) for directory in config.rule_dirs)
    ]
    covered = [e for e in entries if e.covers == "findings"]
    if not targets:
        return _stale(covered, set(), config) if paths is None else []
    known = {rule.identifier for rule in rules}
    report = _run(sorted({rule.file for rule in rules}), targets, root)
    if isinstance(report, str):
        return [Finding("", 0, ERROR, report)]
    findings = _findings(report, known)
    keys = {(e.rule, e.path) for e in covered}
    hit = {(f"semgrep::{f.rule}", f.path) for f in findings}
    remaining = [f for f in findings if (f"semgrep::{f.rule}", f.path) not in keys]
    if paths is None:
        remaining.extend(_stale(covered, hit, config))
    return remaining


def _findings(report: dict[str, Any], known: set[str]) -> list[Finding]:
    findings = [
        Finding(
            str(Path(result["path"])),
            int(result["start"]["line"]),
            _identifier(result["check_id"], known),
            " ".join(str(result["extra"]["message"]).split()),
        )
        for result in report.get("results", [])
    ]
    findings.extend(
        Finding(str(error.get("path", "")), 0, ERROR, _error_text(error))
        for error in report.get("errors", [])
    )
    return findings


def scan_rule(config: Config, identifier: str, paths: tuple[str, ...]) -> list[Finding]:
    """Run one rule alone over the files under paths, ignoring scan_exclude and the record.

    scan_exclude governs the sweep, not a request: the paths named are read, since that is where
    a rule's fixtures live. Paths holding no source file are refused, so a red proof cannot pass
    for green by reaching nothing.
    """
    rules, _ = load_rules(config)
    rule = next((rule for rule in rules if rule.identifier == identifier), None)
    if rule is None:
        msg = f"{identifier} is not a custom rule here; `kotlin-qa rules` lists them"
        raise ValueError(msg)
    targets = [n for n in scope_files(config.root, (), paths) if n.endswith(_SOURCE_SUFFIXES)]
    if not targets:
        msg = f"no Kotlin or Java file under {', '.join(paths)}"
        raise ValueError(msg)
    report = _run([rule.file], targets, config.root)
    if isinstance(report, str):
        return [Finding("", 0, ERROR, report)]
    return _findings(report, {identifier})


def _error_text(error: dict[str, Any]) -> str:
    text = str(error.get("long_msg") or error.get("message") or error.get("type") or "error")
    return f"semgrep could not check this file completely: {' '.join(text.split())}"


def _stale(covered: list[RecordEntry], hit: set[tuple[str, str]], config: Config) -> list[Finding]:
    return [
        Finding(
            config.record.path,
            entry.line,
            STALE,
            f"exception #{entry.number} ({entry.rule}, {entry.path}) covers no finding; remove it",
        )
        for entry in covered
        if (entry.rule, entry.path) not in hit
    ]


def prove_rules(config: Config) -> list[Finding]:
    """Run each rule over its own fixture; the marked lines, and only those, must be flagged."""
    rules, _ = load_rules(config)
    findings: list[Finding] = []
    for rule in rules:
        fixture = rule.fixture
        if fixture is None:
            continue
        findings.extend(_prove(rule, fixture))
    return findings


def _marked(text: str, kind: str, identifier: str) -> set[int]:
    pattern = re.compile(rf"{kind}:[^\n]*(?<![\w.-]){re.escape(identifier)}(?![\w.-])")
    return {number + 1 for number, line in enumerate(text.splitlines(), 1) if pattern.search(line)}


def _prove(rule: Rule, fixture: Path) -> list[Finding]:
    text = fixture.read_text(encoding="utf-8")
    red = _marked(text, "ruleid", rule.identifier)
    green = _marked(text, "ok", rule.identifier)
    report = _run([rule.file], [fixture.name], fixture.parent)
    if isinstance(report, str):
        return [Finding(rule.display, 0, ERROR, f"{rule.identifier}: {report}")]
    known = {rule.identifier}
    flagged = {
        int(result["start"]["line"])
        for result in report.get("results", [])
        if _identifier(result["check_id"], known) == rule.identifier
    }
    problems = [f"misses line {line}, marked ruleid" for line in sorted(red - flagged)]
    problems += [f"flags line {line}, marked ok" for line in sorted(green & flagged)]
    problems += [
        f"flags line {line}, which no ruleid marks" for line in sorted(flagged - red - green)
    ]
    return [
        Finding(rule.display, 0, UNPROVED, f"{rule.identifier} {problem} in {fixture.name}")
        for problem in problems
    ]
