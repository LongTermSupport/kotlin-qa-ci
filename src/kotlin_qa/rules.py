"""Custom detectors: Semgrep rule files, each with a fixture that proves it red and green."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from kotlin_qa.finding import Finding

if TYPE_CHECKING:
    from kotlin_qa.config import Config

BUNDLED_RULES = Path(__file__).parent / "rules"
INVALID = "kqaci.rules.invalid"
UNNAMED = "kqaci.rules.unnamed"
UNTESTED = "kqaci.rules.untested"
_ID = re.compile(r"[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+\Z")
_REQUIRED = ("id", "languages", "severity", "message")
_FIXTURE_SUFFIXES = (".kt", ".java")


@dataclass(frozen=True)
class Rule:
    """One custom detector: its identifier, what it flags, and where it and its fixture live."""

    identifier: str
    message: str
    hazard: str
    file: Path
    display: str
    origin: str  # "bundled" or "project"

    @property
    def fixture(self) -> Path | None:
        """Return the fixture beside the rule file, which carries the red and green examples."""
        for suffix in _FIXTURE_SUFFIXES:
            candidate = self.file.with_suffix(suffix)
            if candidate.is_file():
                return candidate
        return None


def rule_files(config: Config) -> list[tuple[Path, str, str]]:
    """Return every rule file as (path, display name, origin), bundled first."""
    found = [(path, f"kotlin_qa/rules/{path.name}", "bundled") for path in _yaml(BUNDLED_RULES)]
    for directory in config.rule_dirs:
        found.extend(
            (path, path.relative_to(config.root).as_posix(), "project")
            for path in _yaml(config.root / directory)
        )
    return found


def _yaml(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.rglob("*") if p.suffix in {".yml", ".yaml"})


def load_rules(config: Config) -> tuple[list[Rule], list[Finding]]:
    """Read every rule file; a rule that cannot be used is reported and left out."""
    rules: list[Rule] = []
    findings: list[Finding] = []
    seen: dict[str, str] = {}
    for path, display, origin in rule_files(config):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError, UnicodeDecodeError) as error:
            findings.append(Finding(display, 0, INVALID, f"cannot parse: {error}"))
            continue
        entries = data.get("rules") if isinstance(data, dict) else None
        if not isinstance(entries, list) or not entries:
            findings.append(Finding(display, 0, INVALID, "must be a mapping with a rules: list"))
            continue
        for raw in entries:
            rule, problems = _rule(raw, path, display, origin)
            findings.extend(problems)
            if rule is None:
                continue
            if rule.identifier in seen:
                message = f"{rule.identifier} is already defined in {seen[rule.identifier]}"
                findings.append(Finding(display, 0, INVALID, message))
                continue
            seen[rule.identifier] = display
            rules.append(rule)
            findings.extend(_proof_findings(rule))
    return rules, findings


def _rule(raw: Any, path: Path, display: str, origin: str) -> tuple[Rule | None, list[Finding]]:
    if not isinstance(raw, dict):
        return None, [Finding(display, 0, INVALID, "each rule must be a mapping")]
    missing = [key for key in _REQUIRED if not raw.get(key)]
    if missing:
        return None, [Finding(display, 0, INVALID, f"rule lacks {', '.join(missing)}")]
    identifier = str(raw["id"])
    if not _ID.match(identifier):
        return None, [
            Finding(
                display,
                0,
                INVALID,
                f"{identifier}: the id must be dotted lower case, such as kqaci.kt.some-name",
            )
        ]
    metadata = raw.get("metadata")
    hazard = str(metadata.get("hazard", "")).strip() if isinstance(metadata, dict) else ""
    problems = []
    if not hazard:
        problems.append(
            Finding(display, 0, UNNAMED, f"{identifier} names no hazard; add metadata.hazard")
        )
    elif f"kotlin-qa rule-doc {identifier}" not in str(raw["message"]):
        problems.append(
            Finding(
                display,
                0,
                UNNAMED,
                f"{identifier}'s message does not say how to read its documentation; end it "
                f"with `Run: kotlin-qa rule-doc {identifier}`",
            )
        )
    return Rule(identifier, str(raw["message"]), hazard, path, display, origin), problems


def _proof_findings(rule: Rule) -> list[Finding]:
    fixture = rule.fixture
    if fixture is None:
        return [
            Finding(
                rule.display,
                0,
                UNTESTED,
                f"{rule.identifier} has no fixture; add {rule.file.with_suffix('.kt').name} "
                "beside it with `ruleid:` and `ok:` examples",
            )
        ]
    text = fixture.read_text(encoding="utf-8")
    missing = [
        kind
        for kind in ("ruleid", "ok")
        if not re.search(rf"{kind}:[^\n]*(?<![\w.-]){re.escape(rule.identifier)}(?![\w.-])", text)
    ]
    if missing:
        return [
            Finding(
                rule.display,
                0,
                UNTESTED,
                f"{rule.identifier}'s fixture has no `{'` or `'.join(missing)}:` example; a rule "
                "is proved only by a red example it flags and a green one it leaves alone",
            )
        ]
    return []
