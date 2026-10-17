"""The project's changes to the shipped Detekt configuration must each say why.

A rule entry that only switches a rule on needs no reason. Any other content under a rule, such
as switching it off, raising a threshold, excluding a path or ignoring an annotation, loosens
the check, and the line directly above it must be a comment giving the reason.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from kotlin_qa.finding import Finding

if TYPE_CHECKING:
    from kotlin_qa.config import Config

IDENTIFIER = "kqaci.detekt.unjustified"
_ENTRY = re.compile(r"^ {2}[A-Za-z][\w-]*:")
_ACTIVE_ONLY = re.compile(r"^\s*active:\s*true\s*(#.*)?$")
_ENTRY_INDENT = 2


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith("#")


def _block(lines: list[str], start: int) -> list[str]:
    """Return what an entry holds: its own inline value, then the lines indented below it."""
    own = lines[start].split(":", 1)[1].strip()
    body = [own] if own and not own.startswith("#") else []
    for line in lines[start + 1 :]:
        if not line.strip() or _is_comment(line):
            continue
        if len(line) - len(line.lstrip()) <= _ENTRY_INDENT:
            break
        body.append(line)
    return body


def _loosens(body: list[str]) -> bool:
    return not (len(body) == 1 and bool(_ACTIVE_ONLY.match(body[0])))


def check_overrides(config: Config) -> list[Finding]:
    """Return a finding for each loosening rule entry with no comment directly above it."""
    findings: list[Finding] = []
    for name in config.detekt_overrides:
        path = config.root / name
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines):
            if not _ENTRY.match(line):
                continue
            body = _block(lines, number)
            if not body or not _loosens(body):
                continue
            if number > 0 and _is_comment(lines[number - 1]):
                continue
            message = (
                f"{line.strip().rstrip(':')} changes the shipped Detekt configuration with no "
                f"reason in a comment directly above it. Run: kotlin-qa rule-doc {IDENTIFIER}"
            )
            findings.append(Finding(name, number + 1, IDENTIFIER, message))
    return findings
