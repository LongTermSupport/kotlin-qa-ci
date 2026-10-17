"""Tests for the command line: exit codes, output, and the single-rule proof harness."""

import json
from pathlib import Path

import pytest

from kotlin_qa.cli import main

RULE = """\
rules:
  - id: proj.kt.no-sleep
    languages: [kotlin]
    severity: ERROR
    message: "Do not sleep a worker. Run: kotlin-qa rule-doc proj.kt.no-sleep"
    pattern: Thread.sleep($X)
    metadata:
      hazard: A sleeping worker holds its thread and its wake lock for nothing.
"""
FIXTURE = (
    "fun a() {\n    // ruleid: proj.kt.no-sleep\n    Thread.sleep(10)\n"
    "    // ok: proj.kt.no-sleep\n    delay(10)\n}\n"
)


@pytest.fixture
def root(tmp_path: Path, monkeypatch) -> Path:
    (tmp_path / "qa" / "rules").mkdir(parents=True)
    (tmp_path / "qa" / "kotlin-qa.toml").write_text('[summary]\nfile = "AGENTS.md"\n', "utf-8")
    (tmp_path / "qa" / "rules" / "no-sleep.yml").write_text(RULE, "utf-8")
    (tmp_path / "qa" / "rules" / "no-sleep.kt").write_text(FIXTURE, "utf-8")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "Quiet.kt").write_text("fun quiet() = Unit\n", "utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_rule_doc_prints_the_page_for_a_bundled_identifier(root: Path, capsys) -> None:
    assert main(["rule-doc", "kqaci.kt.empty-catch"]) == 0
    assert "## How to fix correctly" in capsys.readouterr().out


def test_rule_doc_for_an_unknown_identifier_fails(root: Path, capsys) -> None:
    assert main(["rule-doc", "nonsense"]) == 1
    assert "no documentation for nonsense" in capsys.readouterr().err


def test_rules_lists_defences_and_the_record(root: Path, capsys) -> None:
    assert main(["rules"]) == 0
    out = capsys.readouterr().out
    assert "kqaci.kt.empty-catch" in out
    assert "proj.kt.no-sleep" in out
    assert "Project record (qa/record.toml): 0 exceptions" in out


def test_rules_json_is_machine_readable(root: Path, capsys) -> None:
    assert main(["rules", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert "proj.kt.no-sleep" in [d["identifier"] for d in data["defences"]]
    assert data["record"] == []


def test_tools_lists_every_lane_and_what_runs_it(root: Path, capsys) -> None:
    assert main(["tools"]) == 0
    out = capsys.readouterr().out
    assert "fmt" in out
    assert "ktlint" in out
    assert "./gradlew --stacktrace testDebugUnitTest" in out


def test_summary_writes_then_checks_clean(root: Path, capsys) -> None:
    assert main(["summary", "--check"]) == 1
    assert main(["summary"]) == 0
    assert main(["summary", "--check"]) == 0
    assert "proj.kt.no-sleep" in (root / "AGENTS.md").read_text("utf-8")


def test_summary_without_a_configured_file_is_a_usage_error(root: Path, capsys) -> None:
    (root / "qa" / "kotlin-qa.toml").write_text("", "utf-8")
    assert main(["summary"]) == 2


def test_docs_check_fails_for_a_project_rule_with_no_page(root: Path, capsys) -> None:
    assert main(["docs-check"]) == 1
    out = capsys.readouterr().out
    assert "qa/defences/proj.kt.no-sleep.md: kqaci.docs.dangling" in out
    assert "proj.kt.no-sleep has no documentation page" in out


def test_record_check_passes_on_an_empty_record(root: Path) -> None:
    assert main(["record", "check"]) == 0


def test_a_bad_configuration_is_exit_two(root: Path, capsys) -> None:
    (root / "qa" / "kotlin-qa.toml").write_text("nonsense = 1\n", "utf-8")
    assert main(["rules"]) == 2
    assert "unknown key nonsense" in capsys.readouterr().err


def test_rule_exits_one_when_the_rule_fires_and_zero_when_it_does_not(root: Path, capsys) -> None:
    assert main(["rule", "proj.kt.no-sleep", "qa/rules/no-sleep.kt"]) == 1
    assert main(["rule", "proj.kt.no-sleep", "app/Quiet.kt"]) == 0


def test_rule_refuses_paths_with_no_source_so_a_red_proof_cannot_pass_by_reaching_nothing(
    root: Path, capsys
) -> None:
    assert main(["rule", "proj.kt.no-sleep", "qa/nowhere"]) == 2
    assert "no Kotlin or Java file" in capsys.readouterr().err


def test_rule_for_an_unknown_rule_is_a_usage_error(root: Path, capsys) -> None:
    assert main(["rule", "proj.kt.absent", "app"]) == 2


def test_rule_runs_the_suppression_detector_alone_on_given_paths(root: Path, capsys) -> None:
    (root / "app" / "Bad.kt").write_text('@Suppress("x")\nclass A\n', "utf-8")
    assert main(["rule", "kqaci.suppression.unrecorded", "app"]) == 1
    assert main(["rule", "kqaci.suppression.unrecorded", "app/Quiet.kt"]) == 0
