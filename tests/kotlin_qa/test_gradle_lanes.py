"""Tests for the lanes that run through Gradle with the library's own init script."""

from pathlib import Path

from kotlin_qa.config import load_config
from kotlin_qa.tools import (
    DETEKT_VERSION,
    detekt_configs,
    external_commands,
    gradle_command,
    init_script,
    shipped_detekt_config,
)


def project(tmp_path: Path, toml: str = "") -> Path:
    (tmp_path / "qa").mkdir()
    (tmp_path / "qa" / "kotlin-qa.toml").write_text(toml, "utf-8")
    return tmp_path


def test_the_init_script_and_the_default_detekt_config_ship_with_the_library() -> None:
    assert init_script().is_file()
    assert shipped_detekt_config().is_file()
    assert "dev.detekt" in init_script().read_text("utf-8")


def test_the_init_script_makes_compiler_warnings_errors() -> None:
    assert "allWarningsAsErrors" in init_script().read_text("utf-8")


def test_every_gradle_lane_runs_with_the_init_script_and_the_pinned_detekt(tmp_path: Path) -> None:
    config = load_config(project(tmp_path))
    for lane in ("lint", "test", "build", "detekt", "coverage"):
        command = gradle_command(config, lane)
        assert command[:2] == ["./gradlew", "--stacktrace"]
        assert command[command.index("-I") + 1] == str(init_script())
        assert f"-Dkqa.detekt.version={DETEKT_VERSION}" in command


def test_the_detekt_lane_runs_the_configured_tasks_last(tmp_path: Path) -> None:
    toml = '[gradle]\ndetekt_tasks = ["detektMain", "detektTest"]\n'
    command = gradle_command(load_config(project(tmp_path, toml)), "detekt")
    assert command[-2:] == ["detektMain", "detektTest"]


def test_detekt_reads_the_shipped_config_then_the_projects_overrides(tmp_path: Path) -> None:
    root = project(tmp_path)
    (root / "qa" / "detekt.yml").write_text("style: {}\n", "utf-8")
    config = load_config(root)
    assert detekt_configs(config) == [shipped_detekt_config(), root / "qa" / "detekt.yml"]
    command = gradle_command(config, "detekt")
    assert f"-Dkqa.detekt.configs={shipped_detekt_config()}:{root / 'qa' / 'detekt.yml'}" in command


def test_a_project_with_no_overrides_file_uses_the_shipped_config_alone(tmp_path: Path) -> None:
    assert detekt_configs(load_config(project(tmp_path))) == [shipped_detekt_config()]


def test_the_coverage_lane_builds_the_report_task(tmp_path: Path) -> None:
    command = gradle_command(load_config(project(tmp_path)), "coverage")
    assert command[-1] == "createDebugUnitTestCoverageReport"


def test_the_shell_lane_checks_tracked_shell_scripts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SHELLCHECK", "shellcheck")
    root = project(tmp_path)
    (root / "ci").mkdir()
    (root / "ci" / "run.sh").write_text("echo hi\n", "utf-8")
    (root / "ci" / "other.bash").write_text("echo hi\n", "utf-8")
    (root / "notes.txt").write_text("x\n", "utf-8")
    commands = external_commands(load_config(root), "shell", None)
    assert commands == [["shellcheck", "ci/other.bash", "ci/run.sh"]]


def test_the_shell_lane_has_nothing_to_run_without_scripts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SHELLCHECK", "shellcheck")
    assert external_commands(load_config(project(tmp_path)), "shell", None) == []


def test_the_workflows_lane_runs_actionlint_then_zizmor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ACTIONLINT", "actionlint")
    monkeypatch.setenv("ZIZMOR", "zizmor")
    root = project(tmp_path)
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "ci.yml").write_text("on: push\n", "utf-8")
    commands = external_commands(load_config(root), "workflows", None)
    assert [c[0] for c in commands] == ["actionlint", "zizmor"]
    assert "--offline" in commands[1]
    assert commands[1][-1] == ".github/workflows"


def test_the_workflows_lane_has_nothing_to_run_without_workflows(tmp_path: Path) -> None:
    assert external_commands(load_config(project(tmp_path)), "workflows", None) == []


def test_the_leaks_lane_scans_the_commit_history_with_the_findings_redacted(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("GITLEAKS", "gitleaks")
    commands = external_commands(load_config(project(tmp_path)), "leaks", None)
    assert commands == [["gitleaks", "git", "--redact", "--no-banner", "."]]
