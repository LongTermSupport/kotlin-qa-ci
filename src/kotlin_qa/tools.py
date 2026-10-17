"""The commands each lane runs: ktlint for format, Gradle for lint, tests and the build."""

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

from kotlin_qa.suppression import project_files, scope_files

if TYPE_CHECKING:
    from kotlin_qa.config import Config

_KTLINT_SUFFIXES = (".kt", ".kts")


class ToolMissingError(Exception):
    """A tool a lane needs is not installed; the message says how to supply it."""


def ktlint_targets(config: Config, paths: tuple[str, ...] | None) -> list[str]:
    """Return the Kotlin files ktlint is given: the project's, or those under paths."""
    names = (
        project_files(config.root, config.scan_exclude)
        if paths is None
        else scope_files(config.root, config.scan_exclude, paths)
    )
    return [name for name in names if name.endswith(_KTLINT_SUFFIXES)]


def ktlint_binary() -> str:
    """Return ktlint from the KTLINT environment variable, else from PATH."""
    chosen = os.environ.get("KTLINT") or shutil.which("ktlint")
    if not chosen:
        msg = (
            "ktlint is not installed; put it on PATH or set KTLINT to its path "
            "(https://github.com/pinterest/ktlint)"
        )
        raise ToolMissingError(msg)
    return chosen


def ktlint_command(config: Config, files: list[str], *, no_fix: bool) -> list[str]:
    """Return the ktlint command: formatting in place, or only checking when no_fix is set."""
    del config
    return [ktlint_binary(), *([] if no_fix else ["--format"]), *files]


def gradle_command(config: Config, lane: str) -> list[str]:
    """Return the Gradle command for the lint, test or build lane."""
    gradle = config.gradle
    task = {"lint": gradle.lint_task, "test": gradle.test_task, "build": gradle.build_task}[lane]
    return [gradle.wrapper, "--stacktrace", task]


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
    if lane in named:
        return named[lane]
    if lane in {"lint", "test", "build"}:
        return " ".join(gradle_command(config, lane))
    check = next((c for c in config.checks if c.name == lane), None)
    return " ".join(check.command) if check else lane
