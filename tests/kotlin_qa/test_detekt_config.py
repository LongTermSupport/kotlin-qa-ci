"""Tests for the rule that a project's loosening of the Detekt configuration says why."""

from pathlib import Path

from kotlin_qa.config import load_config
from kotlin_qa.detekt_config import check_overrides


def overrides(tmp_path: Path, yaml: str) -> list[str]:
    (tmp_path / "qa").mkdir()
    (tmp_path / "qa" / "kotlin-qa.toml").write_text("", "utf-8")
    (tmp_path / "qa" / "detekt.yml").write_text(yaml, "utf-8")
    return [f"{f.line}:{f.rule}" for f in check_overrides(load_config(tmp_path))]


def test_a_relaxed_rule_with_a_reason_above_it_passes(tmp_path: Path) -> None:
    yaml = (
        "style:\n"
        "  # ktlint allows 140 columns, so one limit.\n"
        "  MaxLineLength:\n"
        "    maxLineLength: 140\n"
    )
    assert overrides(tmp_path, yaml) == []


def test_a_relaxed_rule_without_a_reason_is_a_finding_at_its_line(tmp_path: Path) -> None:
    yaml = "style:\n  MaxLineLength:\n    maxLineLength: 200\n"
    assert overrides(tmp_path, yaml) == ["2:kqaci.detekt.unjustified"]


def test_switching_a_rule_off_needs_a_reason(tmp_path: Path) -> None:
    yaml = "naming:\n  FunctionNaming:\n    active: false\n"
    assert overrides(tmp_path, yaml) == ["2:kqaci.detekt.unjustified"]


def test_turning_a_rule_on_needs_no_reason(tmp_path: Path) -> None:
    yaml = "style:\n  MagicNumber:\n    active: true\n"
    assert overrides(tmp_path, yaml) == []


def test_a_reason_covers_only_the_rule_directly_below_it(tmp_path: Path) -> None:
    yaml = (
        "style:\n"
        "  # Reason for the first.\n"
        "  MaxLineLength:\n"
        "    maxLineLength: 140\n"
        "  MagicNumber:\n"
        "    ignoreNumbers: ['7']\n"
    )
    assert overrides(tmp_path, yaml) == ["5:kqaci.detekt.unjustified"]


def test_raising_the_issue_budget_is_a_relaxation_that_needs_a_reason(tmp_path: Path) -> None:
    yaml = "build:\n  maxIssues: 50\n"
    assert overrides(tmp_path, yaml) == ["2:kqaci.detekt.unjustified"]


def test_a_blank_line_between_reason_and_rule_breaks_the_link(tmp_path: Path) -> None:
    yaml = "style:\n  # Reason.\n\n  MaxLineLength:\n    maxLineLength: 140\n"
    assert overrides(tmp_path, yaml) == ["4:kqaci.detekt.unjustified"]


def test_a_missing_overrides_file_has_nothing_to_check(tmp_path: Path) -> None:
    (tmp_path / "qa").mkdir()
    (tmp_path / "qa" / "kotlin-qa.toml").write_text("", "utf-8")
    assert check_overrides(load_config(tmp_path)) == []
