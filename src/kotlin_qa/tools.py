"""The commands each lane runs: ktlint for format, Gradle for lint, tests and the build."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from kotlin_qa.suppression import project_files, scope_files
from kotlin_qa.toolchain import ToolMissingError, resolve

if TYPE_CHECKING:
    from kotlin_qa.config import Config

_KTLINT_SUFFIXES = (".kt", ".kts")
# The Detekt the Gradle lanes run is pinned here, not by the project: a new release can add
# findings, which must arrive as a deliberate bump of this package rather than as a red morning.
DETEKT_VERSION = "2.0.0-alpha.6"
_GRADLE_LANES = ("lint", "test", "build", "detekt", "coverage")


__all__ = ["ToolMissingError"]


def ktlint_targets(config: Config, paths: tuple[str, ...] | None) -> list[str]:
    """Return the Kotlin files ktlint is given: the project's, or those under paths."""
    names = (
        project_files(config.root, config.scan_exclude)
        if paths is None
        else scope_files(config.root, config.scan_exclude, paths)
    )
    return [name for name in names if name.endswith(_KTLINT_SUFFIXES)]


def ktlint_binary() -> str:
    """Return ktlint: the KTLINT variable, an installed pinned copy, else the search path."""
    return resolve("ktlint")


def ktlint_command(config: Config, files: list[str], *, no_fix: bool) -> list[str]:
    """Return the ktlint command: formatting in place, or only checking when no_fix is set."""
    del config
    return [ktlint_binary(), *([] if no_fix else ["--format"]), *files]


_SHELL_SUFFIXES = (".sh", ".bash")
_WORKFLOW_SUFFIXES = (".yml", ".yaml")
_WORKFLOWS = ".github/workflows"


def _lane_files(config: Config, paths: tuple[str, ...] | None) -> list[str]:
    if paths is None:
        return project_files(config.root, config.scan_exclude)
    return scope_files(config.root, config.scan_exclude, paths)


def external_commands(config: Config, lane: str, paths: tuple[str, ...] | None) -> list[list[str]]:
    """Return the commands of a lane that runs a pinned tool, none when it has nothing to check.

    The shell lane checks the project's shell scripts, the workflows lane its GitHub Actions
    workflows (for mistakes, then for insecure patterns), and the leaks lane the commit history
    for committed credentials, with any finding redacted so the report does not repeat it.
    """
    names = _lane_files(config, paths)
    if lane == "shell":
        scripts = [name for name in names if name.endswith(_SHELL_SUFFIXES)]
        return [[resolve("shellcheck"), *scripts]] if scripts else []
    if lane == "workflows":
        flows = [
            name
            for name in names
            if name.startswith(_WORKFLOWS + "/") and name.endswith(_WORKFLOW_SUFFIXES)
        ]
        if not flows:
            return []
        return [
            [resolve("actionlint"), *flows],
            [resolve("zizmor"), "--offline", "--no-progress", _WORKFLOWS],
        ]
    if lane == "leaks":
        return [[resolve("gitleaks"), "git", "--redact", "--no-banner", "."]]
    msg = f"{lane} is not a lane that runs an external tool"
    raise ValueError(msg)


def init_script() -> Path:
    """Return the Gradle init script that adds Detekt, coverage and warnings-as-errors."""
    return Path(__file__).parent / "gradle" / "kotlin-qa.init.gradle"


def shipped_detekt_config() -> Path:
    """Return the Detekt configuration this library ships as the default."""
    return Path(__file__).parent / "configs" / "detekt.yml"


def detekt_configs(config: Config) -> list[Path]:
    """Return the Detekt configurations in order: the shipped one, then the project's overrides."""
    overrides = [config.root / name for name in config.detekt_overrides]
    return [shipped_detekt_config(), *(path for path in overrides if path.is_file())]


def _gradle_tasks(config: Config, lane: str) -> list[str]:
    gradle = config.gradle
    if lane == "detekt":
        return list(gradle.detekt_tasks)
    task = {
        "lint": gradle.lint_task,
        "test": gradle.test_task,
        "build": gradle.build_task,
        "coverage": gradle.coverage_task,
    }[lane]
    return [task]


def gradle_command(config: Config, lane: str) -> list[str]:
    """Return the Gradle command for a lane that runs through the wrapper.

    Every such lane loads the library's init script, so the project's build file needs no change
    to be checked by Detekt, to have its compiler warnings treated as errors, or to measure
    coverage. The pinned Detekt version and the configuration files travel as system properties.
    """
    configs = os.pathsep.join(str(path) for path in detekt_configs(config))
    return [
        config.gradle.wrapper,
        "--stacktrace",
        "-I",
        str(init_script()),
        f"-Dkqa.detekt.version={DETEKT_VERSION}",
        f"-Dkqa.detekt.configs={configs}",
        *_gradle_tasks(config, lane),
    ]


def lane_tool(config: Config, lane: str) -> str:
    """Return what runs a lane, for the tools listing."""
    named = {
        "fmt": "ktlint",
        "record": "kotlin-qa",
        "suppression": "kotlin-qa",
        "summary": "kotlin-qa",
        "docs": "kotlin-qa",
        "rules": "kotlin-qa and Semgrep",
        "semgrep": "Semgrep",
    }
    if lane == "detekt":
        return f"Detekt {DETEKT_VERSION} through Gradle"
    external = {"shell": "ShellCheck", "workflows": "actionlint and zizmor", "leaks": "gitleaks"}
    if lane in external:
        return external[lane]
    if lane in named:
        return named[lane]
    if lane in _GRADLE_LANES:
        return " ".join([config.gradle.wrapper, *_gradle_tasks(config, lane)])
    check = next((c for c in config.checks if c.name == lane), None)
    return " ".join(check.command) if check else lane
