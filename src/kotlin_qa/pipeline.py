"""The run: format, then every detector, then the runners, which run only if all before passed.

A full run checks the whole project. `-p` narrows the format and detector lanes to paths and
runs no runner. Detectors run before tests and the build, so a defence fails the run before
anything slow starts.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from kotlin_qa import __version__
from kotlin_qa.coverage import check_coverage
from kotlin_qa.defences import Defence, active_defences
from kotlin_qa.detekt_config import check_overrides
from kotlin_qa.docs import check_docs
from kotlin_qa.finding import Finding
from kotlin_qa.record import RecordEntry, check_record, load_record
from kotlin_qa.rules import load_rules
from kotlin_qa.semgrep_run import prove_rules, scan_project
from kotlin_qa.summary import check_summary
from kotlin_qa.suppression import suppression_findings
from kotlin_qa.tools import (
    ToolMissingError,
    external_commands,
    gradle_command,
    ktlint_command,
    ktlint_targets,
)

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path
    from typing import TextIO

    from kotlin_qa.config import Config, ProjectCheck

    Runner = Callable[[list[str], Path], int]

METHOD_LINE = (
    "Defence Before Fix (DBF): https://defence-before-fix.github.io/ - agent prompt: "
    "https://defence-before-fix.github.io/defence-before-fix-project-prompt.md"
)
PHASES = (
    ("format", ("fmt",)),
    (
        "detectors",
        (
            "record",
            "suppression",
            "summary",
            "docs",
            "rules",
            "semgrep",
            "shell",
            "workflows",
            "leaks",
            "detekt",
            "lint",
        ),
    ),
    ("runners", ("test", "coverage", "build")),
)
BUILTIN_LANES = frozenset({"record", "suppression", "summary", "docs", "rules", "semgrep"})
# Lanes whose tool prints no identifier of its own: kotlin-qa prints one for each failing step.
_LANE_IDENTIFIERS = {
    "fmt": "kqaci.format",
    "shell": "kqaci.shell",
    "workflows": "kqaci.workflows",
    "leaks": "kqaci.leaks",
    "detekt": "kqaci.detekt",
    "lint": "kqaci.lint",
    "test": "kqaci.tests",
    "build": "kqaci.build",
}
_CANNOT_RUN = 127


class UsageError(Exception):
    """The command line asks for something kotlin-qa does not have."""


def run_subprocess(command: list[str], cwd: Path) -> int:
    """Run one tool with its output going straight to the terminal, and return its exit code."""
    try:
        return subprocess.run(command, cwd=cwd, check=False).returncode
    except OSError as error:
        sys.stdout.write(f"kotlin-qa: cannot run {command[0]}: {error}\n")
        return _CANNOT_RUN


def lane_phases(config: Config) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return the run's phases and their lanes in order, the project's checks among them."""
    detectors = tuple(check.name for check in config.checks if check.phase == "detectors")
    runners = tuple(check.name for check in config.checks if check.phase == "runners")
    detector_lanes = PHASES[1][1]
    return (
        PHASES[0],
        ("detectors", (*detector_lanes[:-1], *detectors, detector_lanes[-1])),
        ("runners", ("test", "coverage", *runners, "build")),
    )


def all_lanes(config: Config) -> tuple[str, ...]:
    """Return every lane name, built in and project, in run order."""
    return tuple(lane for _, lanes in lane_phases(config) for lane in lanes)


@dataclass(frozen=True)
class LaneResult:
    """One lane's outcome in the closing table and the JSON report."""

    name: str
    phase: str
    status: str
    seconds: float | None = None
    note: str = ""


@dataclass
class _Run:
    config: Config
    paths: tuple[str, ...] | None
    out: TextIO
    today: date
    clock: Callable[[], float]
    started: float
    runner: Runner
    no_fix: bool
    entries_cache: tuple[list[RecordEntry], list[Finding]] | None = None
    defences_cache: list[Defence] | None = None
    results: list[LaneResult] = field(default_factory=list)

    def entries(self) -> tuple[list[RecordEntry], list[Finding]]:
        if self.entries_cache is None:
            self.entries_cache = load_record(
                self.config.record_path,
                self.config.record.path,
                today=self.today,
                max_review_days=self.config.record.max_review_days,
            )
        return self.entries_cache

    def defences(self) -> list[Defence]:
        if self.defences_cache is None:
            self.defences_cache = active_defences(self.config)
        return self.defences_cache

    def builtin(self, lane: str) -> list[Finding]:
        entries, invalid = self.entries()
        config = self.config
        if lane == "record":
            return invalid + check_record(entries, config.record, config.record.path, self.today)
        if lane == "suppression":
            return suppression_findings(config, entries, self.paths)
        if lane == "summary":
            return check_summary(config, self.defences(), entries)
        if lane == "rules":
            return load_rules(config)[1] + prove_rules(config)
        if lane == "semgrep":
            return scan_project(config, entries, paths=self.paths)
        return check_docs(config, self.defences())

    def step(self, command: list[str]) -> int:
        self.out.flush()
        return self.runner(command, self.config.root)


def run_pipeline(
    config: Config,
    *,
    requested: tuple[str, ...],
    paths: tuple[str, ...] | None,
    no_fix: bool,
    fail_fast: bool,
    out: TextIO,
    runner: Runner = run_subprocess,
    today: date,
    clock: Callable[[], float] = time.monotonic,
    report: Path | None = None,
    skipped: tuple[str, ...] = (),
) -> int:
    """Run the selected lanes phase by phase and return the exit code: 0 pass, 1 fail.

    With report set, the outcome of every lane is also written there as JSON. Lanes in skipped
    do not run.
    """
    known = all_lanes(config)
    unknown = sorted((set(requested) | set(skipped)) - set(known))
    if unknown:
        msg = f"unknown tool {', '.join(unknown)}; known: {', '.join(known)}"
        raise UsageError(msg)
    if requested and skipped:
        msg = "-t names the lanes to run and --skip the lanes not to; give one of them"
        raise UsageError(msg)
    state = _Run(config, paths, out, today, clock, clock(), runner, no_fix)
    failed = False
    for phase, lanes in lane_phases(config):
        selected = [
            lane for lane in lanes if lane not in skipped and _selected(lane, config, requested)
        ]
        if phase == "runners" and selected and (failed or paths is not None):
            reason = (
                "a format or detector lane failed"
                if failed
                else "-p limits the run to format and detectors"
            )
            out.write(f"kotlin-qa: runners not run: {reason}\n")
            state.results.extend(
                LaneResult(lane, phase, "not run" if lane in selected else "off") for lane in lanes
            )
            break
        for lane in lanes:
            if lane not in selected:
                state.results.append(LaneResult(lane, phase, "skip" if lane in skipped else "off"))
                continue
            out.write(f"== {lane} ==\n")
            out.flush()
            started = clock()
            status, note = _run_lane(state, lane)
            state.results.append(LaneResult(lane, phase, status, clock() - started, note))
            failed = failed or status == "FAIL"
            if failed and fail_fast:
                return _finish(state, failed=True, report=report)
    return _finish(state, failed=failed, report=report)


def _selected(lane: str, config: Config, requested: tuple[str, ...]) -> bool:
    if requested:
        return lane in requested
    if lane not in config.tools:
        return True
    if lane == "summary" and config.summary_file is None:
        return False
    return config.tools[lane]


def _run_lane(state: _Run, lane: str) -> tuple[str, str]:
    """Run one lane and return its status, PASS, FAIL or skip, and a note for the report."""
    config = state.config
    if lane in BUILTIN_LANES:
        return ("PASS" if _report(state.builtin(lane), state.out) else "FAIL"), ""
    check = next((check for check in config.checks if check.name == lane), None)
    if check is not None:
        return _project_check(state, check)
    if lane == "coverage":
        return _coverage(state)
    if lane == "detekt" and (overrides := check_overrides(config)):
        _report(overrides, state.out)
        return "FAIL", "unjustified override"
    return _external_lane(state, lane)


def _external_lane(state: _Run, lane: str) -> tuple[str, str]:
    """Run the tool behind a lane: ktlint or Gradle."""
    try:
        steps = _steps(state, lane)
    except ToolMissingError as error:
        state.out.write(f"kotlin-qa: {lane}: {error}\n")
        return "FAIL", "tool missing"
    if not steps:
        state.out.write(f"kotlin-qa: {lane}: nothing to check within this lane's paths\n")
    for command in steps:
        if state.step(command) != 0:
            identifier = _LANE_IDENTIFIERS[lane]
            state.out.write(
                f"kotlin-qa: {lane} failed: {identifier} (kotlin-qa rule-doc {identifier})\n"
            )
            return "FAIL", ""
    return "PASS", ""


def _coverage(state: _Run) -> tuple[str, str]:
    """Run the coverage task, then hold the report's line coverage to the project's minimum."""
    config = state.config
    if state.step(gradle_command(config, "coverage")) != 0:
        state.out.write(
            f"kotlin-qa: coverage failed: {_LANE_IDENTIFIERS['test']} "
            f"(kotlin-qa rule-doc {_LANE_IDENTIFIERS['test']})\n"
        )
        return "FAIL", "tests failed"
    figure, findings = check_coverage(config)
    if figure is not None:
        state.out.write(
            f"kotlin-qa: line coverage {figure:.1f}% (minimum {config.coverage_minimum:g}%)\n"
        )
    state.out.writelines(finding.render() + "\n" for finding in sorted(findings))
    return ("FAIL" if findings else "PASS"), ""


def _steps(state: _Run, lane: str) -> list[list[str]]:
    config = state.config
    if lane == "fmt":
        files = ktlint_targets(config, state.paths)
        return [ktlint_command(config, files, no_fix=state.no_fix)] if files else []
    if lane in {"shell", "workflows", "leaks"}:
        return external_commands(config, lane, state.paths)
    return [gradle_command(config, lane)]


def _report(findings: list[Finding], out: TextIO) -> bool:
    out.writelines(finding.render() + "\n" for finding in sorted(findings))
    return not findings


def _project_check(state: _Run, check: ProjectCheck) -> tuple[str, str]:
    if state.step(list(check.command)) == 0:
        return "PASS", ""
    state.out.write(
        f"kotlin-qa: {check.name} failed: {check.name} (kotlin-qa rule-doc {check.name})\n"
    )
    return "FAIL", ""


def _finish(state: _Run, *, failed: bool, report: Path | None) -> int:
    out = state.out
    total = state.clock() - state.started
    out.write("\n")
    width = max([12, *(len(result.name) for result in state.results)])
    for result in state.results:
        took = "" if result.seconds is None else f" {result.seconds:>6.1f}s"
        out.write(f"{result.status:8} {result.name:{width}}{took}".rstrip() + "\n")
    out.write(f"{'':8} {'total':{width}} {total:>6.1f}s\n")
    if report is not None:
        _write_report(state, report, failed=failed, total=total)
    if failed:
        out.write(f"\nFAIL\n{METHOD_LINE}\n")
        return 1
    out.write("\nPASS\n")
    return 0


def _write_report(state: _Run, report: Path, *, failed: bool, total: float) -> None:
    data: dict[str, object] = {
        "kotlin_qa": __version__,
        "result": "FAIL" if failed else "PASS",
        "mode": "paths" if state.paths is not None else "full",
        "seconds": round(total, 3),
        "lanes": [
            {
                "name": result.name,
                "phase": result.phase,
                "status": result.status,
                "seconds": None if result.seconds is None else round(result.seconds, 3),
                "note": result.note,
            }
            for result in state.results
        ],
    }
    if state.paths is not None:
        data["paths"] = list(state.paths)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
