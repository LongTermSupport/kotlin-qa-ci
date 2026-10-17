"""Tests for line coverage read from the JaCoCo report."""

from pathlib import Path

import pytest

from kotlin_qa.config import ConfigError, load_config
from kotlin_qa.coverage import check_coverage, line_coverage

REPORT = "app/build/reports/coverage/test/debug/report.xml"


def project(tmp_path: Path, toml: str = "") -> Path:
    (tmp_path / "qa").mkdir()
    (tmp_path / "qa" / "kotlin-qa.toml").write_text(toml, "utf-8")
    return tmp_path


def jacoco(root: Path, missed: int, covered: int) -> None:
    report = root / REPORT
    report.parent.mkdir(parents=True)
    report.write_text(
        '<report name="app"><package name="p"><counter type="LINE" missed="1" covered="1"/>'
        "</package>"
        '<counter type="INSTRUCTION" missed="9" covered="9"/>'
        f'<counter type="LINE" missed="{missed}" covered="{covered}"/></report>',
        "utf-8",
    )


def test_line_coverage_is_read_from_the_report_total_not_a_package(tmp_path: Path) -> None:
    jacoco(tmp_path, missed=75, covered=25)
    assert line_coverage(tmp_path / REPORT) == pytest.approx(25.0)


def test_a_report_with_no_lines_is_fully_covered_not_a_division_error(tmp_path: Path) -> None:
    jacoco(tmp_path, missed=0, covered=0)
    assert line_coverage(tmp_path / REPORT) == pytest.approx(100.0)


def test_coverage_below_the_minimum_is_a_finding(tmp_path: Path) -> None:
    root = project(tmp_path, "[coverage]\nminimum_line = 60\n")
    jacoco(root, missed=75, covered=25)
    figure, findings = check_coverage(load_config(root))
    assert figure == pytest.approx(25.0)
    assert [f.rule for f in findings] == ["kqaci.coverage.below"]
    assert "25.0" in findings[0].message
    assert "60" in findings[0].message


def test_coverage_at_the_minimum_passes(tmp_path: Path) -> None:
    root = project(tmp_path, "[coverage]\nminimum_line = 25\n")
    jacoco(root, missed=75, covered=25)
    assert check_coverage(load_config(root))[1] == []


def test_a_missing_report_is_a_finding_not_a_pass(tmp_path: Path) -> None:
    figure, findings = check_coverage(load_config(project(tmp_path)))
    assert figure is None
    assert [f.rule for f in findings] == ["kqaci.coverage.below"]
    assert "no coverage report" in findings[0].message


def test_an_unreadable_report_is_a_finding_not_a_crash(tmp_path: Path) -> None:
    root = project(tmp_path)
    (root / REPORT).parent.mkdir(parents=True)
    (root / REPORT).write_text("not a report", "utf-8")
    figure, findings = check_coverage(load_config(root))
    assert figure is None
    assert [f.rule for f in findings] == ["kqaci.coverage.below"]


def test_the_minimum_must_be_a_percentage(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"coverage\.minimum_line"):
        load_config(project(tmp_path, "[coverage]\nminimum_line = 140\n"))
