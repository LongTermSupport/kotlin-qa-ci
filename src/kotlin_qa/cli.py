"""The kotlin-qa command: run the pipeline, list defences, resolve identifiers, keep the record."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from kotlin_qa import __version__
from kotlin_qa.config import ConfigError, find_root, load_config
from kotlin_qa.defences import BUILTIN, active_defences
from kotlin_qa.docs import check_docs, resolve
from kotlin_qa.lock import LockHeldError, lock_path, run_lock
from kotlin_qa.pipeline import METHOD_LINE, UsageError, all_lanes, run_pipeline
from kotlin_qa.record import RecordEntry, check_record, load_record
from kotlin_qa.semgrep_run import scan_rule
from kotlin_qa.summary import check_summary, write_summary
from kotlin_qa.suppression import scope_files, suppression_findings
from kotlin_qa.tools import lane_tool

if TYPE_CHECKING:
    from collections.abc import Callable

    from kotlin_qa.config import Config
    from kotlin_qa.finding import Finding

_HARNESS_BUILTINS = frozenset(
    {
        "kqaci.suppression.unrecorded",
        "kqaci.suppression.blanket",
        "kqaci.suppression.unscanned",
    }
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kotlin-qa",
        description="One QA entry point for Kotlin and Android, built for Defence Before Fix.",
        epilog=METHOD_LINE,
    )
    parser.add_argument("--version", action="version", version=f"kotlin-qa {__version__}")
    commands = parser.add_subparsers(dest="command")

    run = commands.add_parser("run", help="format, every detector, then the runners")
    run.add_argument("-t", "--tool", action="append", default=[], dest="tools", help="a lane")
    run.add_argument("--skip", action="append", default=[], help="a lane not to run")
    run.add_argument("-p", "--path", action="append", dest="paths")
    run.add_argument("--json", type=Path, dest="report", help="also write the outcome as JSON")
    run.add_argument("--no-lock", action="store_true", help="run beside another kotlin-qa run")
    run.add_argument("--ci", action="store_true", help="check instead of fixing")
    run.add_argument("--no-fix", action="store_true", help="check instead of fixing")
    run.add_argument("--fail-fast", action="store_true", help="stop at the first failing lane")

    rules = commands.add_parser("rules", help="every active defence and the project record")
    rules.add_argument("--json", action="store_true")

    rule_doc = commands.add_parser("rule-doc", help="documentation for a printed identifier")
    rule_doc.add_argument("identifier")

    rule = commands.add_parser("rule", help="run one rule, on its own, on the paths given")
    rule.add_argument("identifier")
    rule.add_argument("paths", nargs="+")

    commands.add_parser("docs-check", help="fail if a listed identifier has no documentation")

    record = commands.add_parser("record", help="validate or list the project record")
    record.add_argument("action", choices=("check", "list"))

    summary = commands.add_parser("summary", help="write (or check) the agent summary region")
    summary.add_argument("--check", action="store_true")

    commands.add_parser("tools", help="every lane, whether it is on, and its tool")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run kotlin-qa with argv and return its exit code: 0 pass, 1 findings, 2 usage error."""
    args = _parser().parse_args(argv)
    try:
        config = load_config(find_root(Path.cwd()))
        return _dispatch(args, config)
    except (ConfigError, UsageError, ValueError) as error:
        sys.stderr.write(f"kotlin-qa: error: {error}\n")
        return 2
    except LockHeldError as error:
        sys.stderr.write(f"kotlin-qa: {error}\n")
        return 3


def _today() -> date:
    return datetime.now(tz=UTC).date()


def _dispatch(args: argparse.Namespace, config: Config) -> int:
    handlers: dict[str, Callable[[], int]] = {
        "run": lambda: _run(args, config),
        "rules": lambda: _rules(config, as_json=args.json),
        "rule-doc": lambda: _rule_doc(config, args.identifier),
        "rule": lambda: _rule(config, args.identifier, tuple(args.paths)),
        "docs-check": lambda: _report(check_docs(config, active_defences(config))),
        "record": lambda: _record(config, args.action),
        "summary": lambda: _summary(config, check=args.check),
        "tools": lambda: _tools(config),
    }
    return handlers[args.command or "run"]()


def _run(args: argparse.Namespace, config: Config) -> int:
    paths = getattr(args, "paths", None)
    flags = (getattr(args, "no_fix", False), getattr(args, "ci", False))
    held = None if getattr(args, "no_lock", False) else lock_path(config)
    with run_lock(held):
        return run_pipeline(
            config,
            requested=tuple(getattr(args, "tools", [])),
            paths=tuple(paths) if paths else None,
            no_fix=any(flags) or bool(os.environ.get("CI")),
            fail_fast=bool(getattr(args, "fail_fast", False)),
            out=sys.stdout,
            today=_today(),
            report=getattr(args, "report", None),
            skipped=tuple(getattr(args, "skip", [])),
        )


def _entries(config: Config) -> tuple[list[RecordEntry], list[Finding]]:
    return load_record(
        config.record_path,
        config.record.path,
        today=_today(),
        max_review_days=config.record.max_review_days,
    )


def _report(findings: list[Finding]) -> int:
    for finding in sorted(findings):
        sys.stdout.write(finding.render() + "\n")
    return 1 if findings else 0


def _rules(config: Config, *, as_json: bool) -> int:
    defences = active_defences(config)
    entries, _ = _entries(config)
    if as_json:
        data = {
            "defences": [asdict(defence) | {"doc": defence.doc} for defence in defences],
            "record": [
                asdict(entry)
                | {"decided_on": entry.decided_on.isoformat()}
                | {"review_by": entry.review_by.isoformat()}
                for entry in entries
            ],
            "scan_exclude": list(config.scan_exclude),
        }
        sys.stdout.write(json.dumps(data, indent=2) + "\n")
        return 0
    width = max((len(defence.identifier) for defence in defences), default=0)
    for defence in defences:
        sys.stdout.write(
            f"{defence.identifier:{width}}  {defence.tool:9} {defence.origin:8} "
            f"{defence.summary}  ->  {defence.doc}\n"
        )
    noun = "exception" if len(entries) == 1 else "exceptions"
    sys.stdout.write(f"\nProject record ({config.record.path}): {len(entries)} {noun}\n")
    sys.stdout.writelines(_entry_line(entry) for entry in entries)
    if config.scan_exclude:
        sys.stdout.write("\nExcluded from the suppression scan and the Semgrep scan:\n")
        sys.stdout.writelines(f"  {pattern}\n" for pattern in config.scan_exclude)
    return 0


def _entry_line(entry: RecordEntry) -> str:
    return (
        f"  #{entry.number} {entry.rule}  {entry.path}  decided by {entry.decided_by} on "
        f"{entry.decided_on.isoformat()}, review by {entry.review_by.isoformat()}\n"
        f"      {entry.justification}\n"
    )


def _rule_doc(config: Config, identifier: str) -> int:
    text = resolve(identifier, config)
    if text is None:
        sys.stderr.write(f"kotlin-qa: no documentation for {identifier}\n")
        return 1
    sys.stdout.write(text if text.endswith("\n") else text + "\n")
    return 0


def _rule(config: Config, identifier: str, paths: tuple[str, ...]) -> int:
    """Run one rule alone on paths: exit 0 it did not fire, 1 it fired, 2 it could not run."""
    config = replace(config, scan_exclude=())
    check = next((check for check in config.checks if check.name == identifier), None)
    if check is not None:
        msg = f"{identifier} is a project check; run its command directly"
        raise UsageError(msg)
    if identifier in _HARNESS_BUILTINS:
        if not scope_files(config.root, (), paths):
            msg = f"no source file under {', '.join(paths)}"
            raise UsageError(msg)
        entries, _ = _entries(config)
        findings = suppression_findings(config, entries, paths)
        return _report([finding for finding in findings if finding.rule == identifier])
    if identifier in BUILTIN:
        msg = f"{identifier}: run its lane with `kotlin-qa run -t <lane>`; it reads no source"
        raise UsageError(msg)
    findings = scan_rule(config, identifier, paths)
    return _report(findings)


def _record(config: Config, action: str) -> int:
    entries, invalid = _entries(config)
    if action == "list":
        noun = "exception" if len(entries) == 1 else "exceptions"
        sys.stdout.write(
            f"{config.record.path}: {len(entries)} {noun} (max_total {config.record.max_total}, "
            f"max_per_rule {config.record.max_per_rule})\n"
        )
        sys.stdout.writelines(_entry_line(entry) for entry in entries)
        return _report(invalid)
    policy = check_record(entries, config.record, config.record.path, _today())
    return _report(invalid + policy)


def _summary(config: Config, *, check: bool) -> int:
    if config.summary_file is None:
        sys.stderr.write("kotlin-qa: no [summary] file is configured in qa/kotlin-qa.toml\n")
        return 2
    defences = active_defences(config)
    entries, _ = _entries(config)
    if check:
        return _report(check_summary(config, defences, entries))
    write_summary(config, defences, entries)
    sys.stdout.write(f"kotlin-qa: wrote the summary region in {config.summary_file}\n")
    return 0


def _tools(config: Config) -> int:
    lanes = all_lanes(config)
    width = max(len(lane) for lane in lanes)
    for lane in lanes:
        state = "on" if config.tools.get(lane, True) else "off"
        if lane == "summary" and config.summary_file is None:
            state = "off (no summary file)"
        sys.stdout.write(f"{lane:{width}} {state:22} {lane_tool(config, lane)}\n")
    return 0
