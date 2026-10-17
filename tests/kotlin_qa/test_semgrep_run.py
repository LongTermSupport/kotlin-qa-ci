"""Tests for the Semgrep lane: scanning, covering findings with the record, and proving rules.

These run the real Semgrep, so they are few and each makes one scan.
"""

from datetime import date
from pathlib import Path

from kotlin_qa.config import load_config
from kotlin_qa.record import RecordEntry
from kotlin_qa.semgrep_run import ERROR, UNPROVED, prove_rules, scan_project

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
FIXTURE = """\
fun a() {
    // ruleid: proj.kt.no-sleep
    Thread.sleep(10)
    // ok: proj.kt.no-sleep
    delay(10)
}
"""
SOURCE = "fun worker() {\n    Thread.sleep(500)\n}\n"


def project(tmp_path: Path, fixture: str = FIXTURE) -> Path:
    (tmp_path / "qa" / "rules").mkdir(parents=True)
    (tmp_path / "qa" / "rules" / "no-sleep.yml").write_text(RULE, "utf-8")
    (tmp_path / "qa" / "rules" / "no-sleep.kt").write_text(fixture, "utf-8")
    (tmp_path / "app" / "src").mkdir(parents=True)
    (tmp_path / "app" / "src" / "Worker.kt").write_text(SOURCE, "utf-8")
    return tmp_path


def covering(path: str = "app/src/Worker.kt") -> RecordEntry:
    return RecordEntry(
        1,
        "semgrep::proj.kt.no-sleep",
        path,
        "x" * 60,
        "alice",
        date(2026, 1, 1),
        date(2026, 4, 1),
        covers="findings",
    )


def project_findings(findings: list) -> list[tuple[str, int, str]]:
    return [(f.path, f.line, f.rule) for f in findings if f.path.startswith("app/")]


def test_a_project_rule_flags_the_source_it_matches(tmp_path: Path) -> None:
    config = load_config(project(tmp_path))
    found = scan_project(config, [], paths=None)
    assert project_findings(found) == [("app/src/Worker.kt", 2, "proj.kt.no-sleep")]
    assert "Run: kotlin-qa rule-doc proj.kt.no-sleep" in found[0].message


def test_the_fixtures_of_the_rules_are_proved_not_scanned_as_project_source(tmp_path: Path) -> None:
    found = scan_project(load_config(project(tmp_path)), [], paths=None)
    assert [f.path for f in found] == ["app/src/Worker.kt"]


def test_a_recorded_exception_covers_the_findings_of_its_rule_in_its_file(tmp_path: Path) -> None:
    config = load_config(project(tmp_path))
    assert project_findings(scan_project(config, [covering()], paths=None)) == []


def test_an_exception_for_another_file_covers_nothing_and_is_stale(tmp_path: Path) -> None:
    config = load_config(project(tmp_path))
    found = scan_project(config, [covering("app/src/Other.kt")], paths=None)
    assert project_findings(found) == [("app/src/Worker.kt", 2, "proj.kt.no-sleep")]
    assert [f.rule for f in found if f.path == "qa/record.toml"] == ["kqaci.record.stale"]


def test_a_nosem_comment_does_not_silence_a_rule(tmp_path: Path) -> None:
    root = project(tmp_path)
    (root / "app" / "src" / "Worker.kt").write_text(
        "fun worker() {\n    Thread.sleep(500) // nosemgrep: proj.kt.no-sleep\n}\n", "utf-8"
    )
    found = scan_project(load_config(root), [], paths=None)
    assert project_findings(found) == [("app/src/Worker.kt", 2, "proj.kt.no-sleep")]


def test_a_semgrepignore_file_does_not_hide_a_file_from_the_scan(tmp_path: Path) -> None:
    root = project(tmp_path)
    (root / ".semgrepignore").write_text("app/\n", "utf-8")
    found = scan_project(load_config(root), [], paths=None)
    assert project_findings(found) == [("app/src/Worker.kt", 2, "proj.kt.no-sleep")]


def test_a_narrow_scan_reads_only_the_paths_and_judges_no_stale_entry(tmp_path: Path) -> None:
    root = project(tmp_path)
    (root / "app" / "src" / "Quiet.kt").write_text("fun quiet() = Unit\n", "utf-8")
    config = load_config(root)
    found = scan_project(config, [covering("app/src/Other.kt")], paths=("app/src/Quiet.kt",))
    assert found == []


def test_a_rule_whose_fixture_agrees_with_it_is_proved(tmp_path: Path) -> None:
    config = load_config(project(tmp_path))
    assert [f for f in prove_rules(config) if f.path.startswith("qa/")] == []


def test_a_fixture_marking_a_line_the_rule_misses_is_unproved(tmp_path: Path) -> None:
    missed = FIXTURE.replace("Thread.sleep(10)", "Thread.yield()")
    config = load_config(project(tmp_path, missed))
    found = [f for f in prove_rules(config) if f.path.startswith("qa/")]
    assert [f.rule for f in found] == [UNPROVED]
    assert "misses" in found[0].message


def test_a_green_line_the_rule_flags_is_unproved(tmp_path: Path) -> None:
    flagged = FIXTURE.replace("delay(10)", "Thread.sleep(20)")
    config = load_config(project(tmp_path, flagged))
    found = [f for f in prove_rules(config) if f.path.startswith("qa/")]
    assert [f.rule for f in found] == [UNPROVED]
    assert "flags" in found[0].message


def test_semgrep_failing_to_read_a_file_is_a_finding_not_a_pass(tmp_path: Path) -> None:
    root = project(tmp_path)
    (root / "app" / "src" / "Broken.kt").write_text("fun (((( {{{\n", "utf-8")
    found = scan_project(load_config(root), [], paths=None)
    assert ERROR in [f.rule for f in found]
