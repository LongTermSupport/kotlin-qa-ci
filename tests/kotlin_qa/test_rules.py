"""Tests for loading custom detectors and holding each to a fixture that proves it."""

from pathlib import Path

from kotlin_qa.config import load_config
from kotlin_qa.rules import INVALID, UNNAMED, UNTESTED, load_rules

GOOD_RULE = """\
rules:
  - id: proj.kt.no-sleep
    languages: [kotlin]
    severity: ERROR
    message: "Do not sleep a worker. Run: kotlin-qa rule-doc proj.kt.no-sleep"
    pattern: Thread.sleep($X)
    metadata:
      hazard: A sleeping worker holds its thread and its wake lock for nothing.
"""
GOOD_FIXTURE = """\
fun a() {
    // ruleid: proj.kt.no-sleep
    Thread.sleep(10)
    // ok: proj.kt.no-sleep
    delay(10)
}
"""


def project(tmp_path: Path, rule: str = GOOD_RULE, fixture: str | None = GOOD_FIXTURE) -> Path:
    (tmp_path / "qa" / "rules").mkdir(parents=True)
    (tmp_path / "qa" / "rules" / "no-sleep.yml").write_text(rule, encoding="utf-8")
    if fixture is not None:
        (tmp_path / "qa" / "rules" / "no-sleep.kt").write_text(fixture, encoding="utf-8")
    return tmp_path


def project_rules(root: Path) -> tuple[list[str], list[tuple[str, str]]]:
    rules, findings = load_rules(load_config(root))
    return (
        [rule.identifier for rule in rules if rule.origin == "project"],
        [(f.rule, f.message) for f in findings if f.path.startswith("qa/")],
    )


def test_a_rule_with_a_hazard_a_pointer_and_a_proving_fixture_loads(tmp_path: Path) -> None:
    assert project_rules(project(tmp_path)) == (["proj.kt.no-sleep"], [])


def test_a_rule_without_a_fixture_is_untested(tmp_path: Path) -> None:
    ids, findings = project_rules(project(tmp_path, fixture=None))
    assert ids == ["proj.kt.no-sleep"]
    assert [rule for rule, _ in findings] == [UNTESTED]


def test_a_fixture_without_a_green_example_is_untested(tmp_path: Path) -> None:
    red_only = "fun a() {\n    // ruleid: proj.kt.no-sleep\n    Thread.sleep(10)\n}\n"
    _, findings = project_rules(project(tmp_path, fixture=red_only))
    assert [rule for rule, _ in findings] == [UNTESTED]
    assert "ok:" in findings[0][1]


def test_an_example_for_another_rule_does_not_prove_this_one(tmp_path: Path) -> None:
    other = GOOD_FIXTURE.replace("proj.kt.no-sleep", "proj.kt.no-sleep-longer")
    _, findings = project_rules(project(tmp_path, fixture=other))
    assert [rule for rule, _ in findings] == [UNTESTED]


def test_a_rule_that_names_no_hazard_is_unnamed(tmp_path: Path) -> None:
    rule = GOOD_RULE.replace("    metadata:\n      hazard: A sleeping worker holds its thread and its wake lock for nothing.\n", "")
    _, findings = project_rules(project(tmp_path, rule))
    assert [r for r, _ in findings] == [UNNAMED]


def test_a_message_that_does_not_point_at_the_docs_is_unnamed(tmp_path: Path) -> None:
    rule = GOOD_RULE.replace(" Run: kotlin-qa rule-doc proj.kt.no-sleep", "")
    _, findings = project_rules(project(tmp_path, rule))
    assert [r for r, _ in findings] == [UNNAMED]


def test_a_rule_missing_required_keys_is_invalid_and_left_out(tmp_path: Path) -> None:
    ids, findings = project_rules(project(tmp_path, "rules:\n  - id: proj.kt.x\n"))
    assert ids == []
    assert [rule for rule, _ in findings] == [INVALID]


def test_an_id_that_is_not_dotted_lower_case_is_invalid(tmp_path: Path) -> None:
    ids, findings = project_rules(project(tmp_path, GOOD_RULE.replace("proj.kt.no-sleep", "NoSleep")))
    assert ids == []
    assert [rule for rule, _ in findings] == [INVALID]


def test_a_file_that_is_not_yaml_is_invalid(tmp_path: Path) -> None:
    ids, findings = project_rules(project(tmp_path, "rules: [unclosed"))
    assert ids == []
    assert [rule for rule, _ in findings] == [INVALID]


def test_an_id_defined_twice_is_reported(tmp_path: Path) -> None:
    root = project(tmp_path)
    (root / "qa" / "rules" / "again.yml").write_text(GOOD_RULE, encoding="utf-8")
    ids, findings = project_rules(root)
    assert ids == ["proj.kt.no-sleep"]
    assert any(rule == INVALID and "already defined" in message for rule, message in findings)
