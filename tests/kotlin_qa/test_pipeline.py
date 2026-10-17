"""Tests for the run: phase order, the runner gate, the closing table and the JSON report."""

import io
import json
from datetime import date
from pathlib import Path

import pytest

from kotlin_qa.config import load_config
from kotlin_qa.pipeline import UsageError, all_lanes, run_pipeline

TODAY = date(2026, 3, 1)
QUIET = ""
SLOW = ("rules", "semgrep", "lint")
STATUSES = {"PASS", "off", "skip"}


class Recorder:
    """A runner that records each command and fails those whose first words are in fail."""

    def __init__(self, *fail: str) -> None:
        self.commands: list[list[str]] = []
        self.fail = fail

    def __call__(self, command: list[str], cwd: Path) -> int:
        self.commands.append(command)
        return 1 if any(word in command for word in self.fail) else 0

    def names(self) -> list[str]:
        return [Path(command[0]).name for command in self.commands]


def project(tmp_path: Path, toml: str = QUIET) -> Path:
    (tmp_path / "qa").mkdir()
    (tmp_path / "qa" / "kotlin-qa.toml").write_text(toml, "utf-8")
    (tmp_path / "app" / "src").mkdir(parents=True)
    (tmp_path / "app" / "src" / "A.kt").write_text("class A\n", "utf-8")
    return tmp_path


def run(root: Path, runner: Recorder, **kwargs) -> tuple[int, str]:
    out = io.StringIO()
    options = {
        "requested": (),
        "paths": None,
        "no_fix": True,
        "fail_fast": False,
        "skipped": SLOW,
    } | kwargs
    code = run_pipeline(
        load_config(root), out=out, runner=runner, today=TODAY, clock=lambda: 0.0, **options
    )
    return code, out.getvalue()


@pytest.fixture(autouse=True)
def ktlint(monkeypatch) -> None:
    monkeypatch.setenv("KTLINT", "ktlint")


def test_a_clean_project_formats_checks_then_runs_tests_and_the_build(tmp_path: Path) -> None:
    runner = Recorder()
    code, out = run(project(tmp_path), runner)
    assert code == 0
    assert runner.names() == ["ktlint", "gradlew", "gradlew"]
    assert [c[-1] for c in runner.commands[1:]] == ["testDebugUnitTest", "assembleDebug"]
    assert out.rstrip().endswith("PASS")


def test_the_closing_table_lists_every_lane_in_order(tmp_path: Path) -> None:
    _, out = run(project(tmp_path), Recorder())
    rows = [line.split() for line in out.splitlines() if line[:8].strip() in STATUSES]
    lanes = [row[1] for row in rows if len(row) > 1]
    assert lanes == list(all_lanes(load_config(tmp_path)))


def test_a_failing_format_lane_fails_the_run_and_stops_the_runners(tmp_path: Path) -> None:
    runner = Recorder("ktlint")
    code, out = run(project(tmp_path), runner)
    assert code == 1
    assert "kqaci.format" in out
    assert runner.names() == ["ktlint"]
    assert "runners not run" in out


def test_a_failing_detector_stops_the_runners_but_not_the_other_detectors(tmp_path: Path) -> None:
    root = project(tmp_path)
    (root / "app" / "src" / "A.kt").write_text('@Suppress("x")\nclass A\n', "utf-8")
    runner = Recorder()
    code, out = run(root, runner)
    assert code == 1
    assert "kqaci.suppression.unrecorded" in out
    assert "gradlew" not in runner.names()
    assert "== docs ==" in out


def test_a_failing_test_lane_fails_with_its_identifier_and_still_reports_the_build(
    tmp_path: Path,
) -> None:
    code, out = run(project(tmp_path), Recorder("testDebugUnitTest"))
    assert code == 1
    assert "kqaci.tests" in out


def test_fail_fast_stops_at_the_first_failing_lane(tmp_path: Path) -> None:
    root = project(tmp_path)
    (root / "app" / "src" / "A.kt").write_text('@Suppress("x")\nclass A\n', "utf-8")
    _, out = run(root, Recorder(), fail_fast=True)
    assert "== docs ==" not in out


def test_named_paths_run_no_runner(tmp_path: Path) -> None:
    runner = Recorder()
    code, out = run(project(tmp_path), runner, paths=("app/src",))
    assert code == 0
    assert runner.names() == ["ktlint"]
    assert "-p limits the run" in out


def test_requested_lanes_are_the_only_ones_run(tmp_path: Path) -> None:
    runner = Recorder()
    run(project(tmp_path), runner, requested=("fmt",), skipped=())
    assert runner.names() == ["ktlint"]


def test_an_unknown_lane_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(UsageError, match="unknown tool nonsense"):
        run(project(tmp_path), Recorder(), requested=("nonsense",))


def test_requesting_and_skipping_together_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(UsageError, match="give one of them"):
        run(project(tmp_path), Recorder(), requested=("fmt",), skipped=("test",))


def test_a_project_check_runs_in_its_phase_and_fails_the_run_with_its_name(tmp_path: Path) -> None:
    toml = QUIET + (
        '[[check]]\nname = "spelling"\ncommand = ["spell", "--all"]\n'
        'description = "d"\ndoc = "qa/s.md"\n'
    )
    runner = Recorder("spell")
    code, out = run(project(tmp_path, toml), runner)
    assert code == 1
    assert "spelling" in out
    assert "kotlin-qa rule-doc spelling" in out
    assert "gradlew" not in runner.names()


def test_the_json_report_records_every_lane(tmp_path: Path) -> None:
    report = tmp_path / "out" / "report.json"
    run(project(tmp_path), Recorder(), report=report)
    data = json.loads(report.read_text())
    assert data["result"] == "PASS"
    assert data["mode"] == "full"
    assert [lane["name"] for lane in data["lanes"]] == list(all_lanes(load_config(tmp_path)))


def test_the_closing_failure_message_points_at_the_method(tmp_path: Path) -> None:
    _, out = run(project(tmp_path), Recorder("ktlint"))
    assert "https://defence-before-fix.github.io/" in out
