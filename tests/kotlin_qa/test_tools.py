"""Tests for the commands each lane runs."""

from pathlib import Path

import pytest

from kotlin_qa.config import load_config
from kotlin_qa.tools import ToolMissingError, gradle_command, ktlint_command, ktlint_targets

GRADLE = '[gradle]\nwrapper = "./gradlew"\nlint_task = "lint"\n'


def project(tmp_path: Path, toml: str = "") -> Path:
    (tmp_path / "qa").mkdir()
    (tmp_path / "qa" / "kotlin-qa.toml").write_text(toml, "utf-8")
    (tmp_path / "app" / "src").mkdir(parents=True)
    (tmp_path / "app" / "src" / "A.kt").write_text("class A\n", "utf-8")
    (tmp_path / "app" / "build.gradle.kts").write_text("plugins {}\n", "utf-8")
    (tmp_path / "app" / "src" / "Notes.txt").write_text("x\n", "utf-8")
    return tmp_path


def test_ktlint_checks_kotlin_files_and_scripts_only(tmp_path: Path) -> None:
    config = load_config(project(tmp_path))
    assert ktlint_targets(config, None) == ["app/build.gradle.kts", "app/src/A.kt"]


def test_named_paths_narrow_the_ktlint_files(tmp_path: Path) -> None:
    config = load_config(project(tmp_path))
    assert ktlint_targets(config, ("app/src",)) == ["app/src/A.kt"]


def test_ktlint_formats_unless_told_to_only_check(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("KTLINT", "/opt/ktlint")
    config = load_config(project(tmp_path))
    files = ["app/src/A.kt"]
    assert ktlint_command(config, files, no_fix=False) == ["/opt/ktlint", "--format", *files]
    assert ktlint_command(config, files, no_fix=True) == ["/opt/ktlint", *files]


def test_a_missing_ktlint_is_an_error_naming_how_to_supply_it(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("KTLINT", raising=False)
    monkeypatch.setenv("KOTLIN_QA_HOME", str(tmp_path / "empty-cache"))
    monkeypatch.setenv("PATH", str(tmp_path))
    config = load_config(project(tmp_path))
    with pytest.raises(ToolMissingError, match="KTLINT"):
        ktlint_command(config, ["app/src/A.kt"], no_fix=True)


def test_gradle_runs_the_wrapper_with_the_configured_task(tmp_path: Path) -> None:
    config = load_config(project(tmp_path, GRADLE))
    assert gradle_command(config, "lint")[-1] == "lint"
    assert gradle_command(config, "test")[-1] == "testDebugUnitTest"
    assert gradle_command(config, "build")[-1] == "assembleDebug"
    assert gradle_command(config, "build")[0] == "./gradlew"
