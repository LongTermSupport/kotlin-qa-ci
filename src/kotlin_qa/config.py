"""qa/kotlin-qa.toml: every key, its default, and its validation."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

QA_DIR_NAME = "qa"
CONFIG_FILE = f"{QA_DIR_NAME}/kotlin-qa.toml"
# Every lane the run knows, in the order it runs them. summary is on, but only does anything when
# a summary file is named.
TOOLS = (
    "fmt",
    "record",
    "suppression",
    "summary",
    "docs",
    "rules",
    "semgrep",
    "lint",
    "test",
    "build",
)
CHECK_PHASES = ("detectors", "runners")

_TOP_KEYS = frozenset(
    {
        "record",
        "docs_dir",
        "rule_dirs",
        "scan_exclude",
        "tools",
        "summary",
        "gradle",
        "lock",
        "check",
    }
)
_RECORD_KEYS = frozenset({"path", "max_total", "max_per_rule", "max_review_days"})
_GRADLE_KEYS = frozenset({"wrapper", "test_task", "lint_task", "build_task"})
_CHECK_KEYS = frozenset({"name", "command", "description", "doc", "phase", "files"})
_CHECK_NAME = re.compile(r"[a-z][a-z0-9_-]*\Z")


class ConfigError(Exception):
    """The configuration cannot be used; the message names the key."""


@dataclass(frozen=True)
class RecordPolicy:
    """Where the project record lives and the limits that keep it small."""

    path: str = "qa/record.toml"
    max_total: int = 20
    max_per_rule: int = 5
    max_review_days: int = 180


@dataclass(frozen=True)
class GradleConfig:
    """The Gradle wrapper and the task each lane runs."""

    wrapper: str = "./gradlew"
    test_task: str = "testDebugUnitTest"
    lint_task: str = "lintDebug"
    build_task: str = "assembleDebug"


@dataclass(frozen=True)
class ProjectCheck:
    """A check the project supplies: a command run as a lane of its own."""

    name: str
    command: tuple[str, ...]
    description: str
    doc: str
    phase: str = "detectors"
    files: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Config:
    """The resolved configuration for one project root."""

    root: Path
    record: RecordPolicy = field(default_factory=RecordPolicy)
    docs_dir: str = "qa/defences"
    rule_dirs: tuple[str, ...] = ("qa/rules",)
    scan_exclude: tuple[str, ...] = ()
    tools: dict[str, bool] = field(default_factory=lambda: dict.fromkeys(TOOLS, True))
    summary_file: str | None = None
    gradle: GradleConfig = field(default_factory=GradleConfig)
    checks: tuple[ProjectCheck, ...] = ()
    lock: bool = True

    @property
    def record_path(self) -> Path:
        """Return the record's absolute path."""
        return self.root / self.record.path


def find_root(start: Path) -> Path:
    """Return the nearest directory at or above start that holds the configuration file.

    A project with no configuration file runs on the defaults from where the command ran.
    """
    for candidate in (start, *start.parents):
        if (candidate / CONFIG_FILE).is_file():
            return candidate
    return start


def load_config(root: Path) -> Config:
    """Read the configuration at root, or the defaults when there is no file."""
    path = root / CONFIG_FILE
    if not path.is_file():
        return Config(root=root)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        msg = f"{CONFIG_FILE}: cannot parse: {error}"
        raise ConfigError(msg) from error
    unknown = sorted(set(data) - _TOP_KEYS)
    if unknown:
        msg = f"{CONFIG_FILE}: unknown key {unknown[0]}"
        raise ConfigError(msg)
    record = _record(data.get("record", {}))
    return Config(
        root=root,
        record=record,
        docs_dir=_string(data, "docs_dir", "qa/defences"),
        rule_dirs=_strings(data, "rule_dirs", ("qa/rules",)),
        scan_exclude=_strings(data, "scan_exclude", ()),
        tools=_tools(data.get("tools", {})),
        summary_file=_summary(data.get("summary", {})),
        gradle=_gradle(data.get("gradle", {})),
        checks=_checks(data.get("check", [])),
        lock=_boolean(data, "lock", default=True),
    )


def _string(data: dict[str, Any], key: str, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        msg = f"{key} must be a non-empty string"
        raise ConfigError(msg)
    return value


def _strings(data: dict[str, Any], key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = data.get(key, list(default))
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        msg = f"{key} must be a list of strings"
        raise ConfigError(msg)
    return tuple(value)


def _boolean(data: dict[str, Any], key: str, *, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        msg = f"{key} must be true or false"
        raise ConfigError(msg)
    return value


def _table(value: object, name: str, allowed: frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        msg = f"{name} must be a table"
        raise ConfigError(msg)
    unknown = sorted(set(value) - allowed)
    if unknown:
        msg = f"unknown key {name}.{unknown[0]}"
        raise ConfigError(msg)
    return value


def _record(value: object) -> RecordPolicy:
    table = _table(value, "record", _RECORD_KEYS)
    defaults = RecordPolicy()
    path = table.get("path", defaults.path)
    if not isinstance(path, str) or not path.strip():
        msg = "record.path must be a non-empty string"
        raise ConfigError(msg)
    numbers = {}
    for key in ("max_total", "max_per_rule", "max_review_days"):
        number = table.get(key, getattr(defaults, key))
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            msg = f"record.{key} must be a positive integer"
            raise ConfigError(msg)
        numbers[key] = number
    return RecordPolicy(path=path, **numbers)


def _tools(value: object) -> dict[str, bool]:
    if not isinstance(value, dict):
        msg = "tools must be a table"
        raise ConfigError(msg)
    tools = dict.fromkeys(TOOLS, True)
    for name, state in value.items():
        if name not in tools:
            msg = f"unknown tool {name}; known: {', '.join(TOOLS)}"
            raise ConfigError(msg)
        if not isinstance(state, bool):
            msg = f"tools.{name} must be true or false"
            raise ConfigError(msg)
        tools[name] = state
    return tools


def _summary(value: object) -> str | None:
    table = _table(value, "summary", frozenset({"file"}))
    file = table.get("file")
    if file is not None and (not isinstance(file, str) or not file.strip()):
        msg = "summary.file must be a non-empty string"
        raise ConfigError(msg)
    return file


def _gradle(value: object) -> GradleConfig:
    table = _table(value, "gradle", _GRADLE_KEYS)
    defaults = GradleConfig()
    settings = {}
    for key in _GRADLE_KEYS:
        text = table.get(key, getattr(defaults, key))
        if not isinstance(text, str) or not text.strip():
            msg = f"gradle.{key} must be a string"
            raise ConfigError(msg)
        settings[key] = text
    return GradleConfig(**settings)


def _checks(value: object) -> tuple[ProjectCheck, ...]:
    if not isinstance(value, list):
        msg = "check must be [[check]] tables"
        raise ConfigError(msg)
    checks = []
    for number, raw in enumerate(value, start=1):
        label = f"check #{number}"
        if not isinstance(raw, dict):
            msg = f"{label} must be a table"
            raise ConfigError(msg)
        unknown = sorted(set(raw) - _CHECK_KEYS)
        if unknown:
            msg = f"{label}: unknown key {unknown[0]}"
            raise ConfigError(msg)
        checks.append(_check(raw, label))
    names = [check.name for check in checks]
    for name in names:
        if names.count(name) > 1:
            msg = f"check name {name} is used twice"
            raise ConfigError(msg)
    return tuple(checks)


def _check(raw: dict[str, Any], label: str) -> ProjectCheck:
    for key in ("name", "command", "description", "doc"):
        if key not in raw:
            msg = f"{label}: {key} is missing"
            raise ConfigError(msg)
    name = raw["name"]
    if not isinstance(name, str) or not _CHECK_NAME.match(name):
        msg = f"{label}: name must be lower case letters, digits, - and _, starting with a letter"
        raise ConfigError(msg)
    if name in TOOLS:
        msg = f"{label}: name {name} is already a tool"
        raise ConfigError(msg)
    command = raw["command"]
    if not isinstance(command, list) or not command or not all(isinstance(a, str) for a in command):
        msg = f"{label}: command must be a non-empty list of strings"
        raise ConfigError(msg)
    for key in ("description", "doc"):
        if not isinstance(raw[key], str) or not raw[key].strip():
            msg = f"{label}: {key} must be a non-empty string"
            raise ConfigError(msg)
    phase = raw.get("phase", "detectors")
    if phase not in CHECK_PHASES:
        msg = f"{label}: phase must be one of {', '.join(CHECK_PHASES)}"
        raise ConfigError(msg)
    files = raw.get("files")
    if files is not None and (
        not isinstance(files, list) or not all(isinstance(item, str) for item in files)
    ):
        msg = f"{label}: files must be a list of globs"
        raise ConfigError(msg)
    return ProjectCheck(
        name=name,
        command=tuple(command),
        description=raw["description"],
        doc=raw["doc"],
        phase=phase,
        files=None if files is None else tuple(files),
    )
