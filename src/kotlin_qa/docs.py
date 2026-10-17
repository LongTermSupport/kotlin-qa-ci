"""Resolving any printed identifier to its documentation, offline, and the dangling-docs check."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from kotlin_qa.finding import Finding

if TYPE_CHECKING:
    from kotlin_qa.config import Config, ProjectCheck
    from kotlin_qa.defences import Defence

BUNDLED_DOCS = Path(__file__).parent / "docs"
DANGLING = "kqaci.docs.dangling"
REQUIRED_SECTIONS = ("## What it flags", "## Why", "## How to fix correctly")
_PREFIX = re.compile(r"^(?:ktlint|semgrep|lint|kotlin|idea|kqa)::")
# Tools whose rules kotlin-qa runs or routes but whose catalogues it does not bundle.
_TOOLS = {
    "ktlint": "ktlint",
    "lint": "Android Lint",
    "kotlin": "the Kotlin compiler",
    "idea": "the IntelliJ inspections",
    "semgrep": "Semgrep",
    "kqa": "kotlin-qa's own configuration",
}


def missing_sections(page: str) -> list[str]:
    """Return the required headings a documentation page lacks."""
    headings = {line.strip() for line in page.splitlines()}
    return [section for section in REQUIRED_SECTIONS if section not in headings]


def resolve(identifier: str, config: Config) -> str | None:
    """Return the documentation for an identifier exactly as printed, or None if nothing has it.

    The order is the bundled pages, the project's own pages under docs_dir, the project's
    checks, then a route page for an identifier that belongs to a tool whose catalogue is not
    bundled.
    """
    name = _PREFIX.sub("", identifier)
    for directory in (BUNDLED_DOCS, config.root / config.docs_dir):
        page = directory / f"{name}.md"
        if page.is_file():
            return page.read_text(encoding="utf-8")
    check = next((check for check in config.checks if check.name == name), None)
    if check is not None:
        return _check_doc(check, config)
    return _route_doc(identifier)


def _check_doc(check: ProjectCheck, config: Config) -> str:
    lines = [f"# {check.name}, a project check", "", check.description, ""]
    lines.append(f"Run as: {' '.join(check.command)}")
    lines.append(f"Documented in: {check.doc}")
    body = doc_text(config.root / check.doc)
    if body:
        lines.extend(["", body])
    return "\n".join(lines) + "\n"


def doc_text(path: Path) -> str:
    """Return a check's documentation: a script's leading comment block, else the whole file."""
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
    if path.suffix in {".sh", ".bash"} or text.startswith("#!"):
        block: list[str] = []
        for line in text.splitlines():
            if line.startswith("#!") and not block:
                continue
            if not line.startswith("#"):
                break
            block.append(line[1:].removeprefix(" "))
        if block:
            return "\n".join(block).strip()
    return text.strip()


def _route_doc(identifier: str) -> str | None:
    tool, separator, name = identifier.partition("::")
    if not separator or tool not in _TOOLS or not name:
        return None
    label = _TOOLS[tool]
    return (
        f"# {identifier}\n\nThe {label} identifier `{name}`. kotlin-qa does not bundle {label}'s "
        f"catalogue, so its own documentation describes the identifier.\n\nUsed in a suppression "
        "or a setting, it names a route that silences a detector. kotlin-qa holds every use of "
        "it to the project record: a use without an exception for this identifier and that file "
        "is reported as kqaci.suppression.unrecorded "
        "(`kotlin-qa rule-doc kqaci.suppression.unrecorded`).\n"
    )


def check_docs(config: Config, defences: list[Defence]) -> list[Finding]:
    """Report every bundled or project defence whose page is missing or incomplete."""
    findings: list[Finding] = []
    for defence in defences:
        if defence.tool == "check":
            findings.extend(_check_doc_findings(defence, config))
            continue
        directory = BUNDLED_DOCS if defence.origin == "bundled" else config.root / config.docs_dir
        page = directory / f"{defence.identifier}.md"
        display = (
            f"{config.docs_dir}/{page.name}" if defence.origin == "project" else page.as_posix()
        )
        if not page.is_file():
            findings.append(
                Finding(display, 0, DANGLING, f"{defence.identifier} has no documentation page")
            )
            continue
        missing = missing_sections(page.read_text(encoding="utf-8"))
        if missing:
            findings.append(
                Finding(
                    display, 0, DANGLING, f"{defence.identifier}'s page lacks: {', '.join(missing)}"
                )
            )
    return findings


def _check_doc_findings(defence: Defence, config: Config) -> list[Finding]:
    check = next(check for check in config.checks if check.name == defence.identifier)
    path = config.root / check.doc
    if not path.is_file():
        message = f"{check.name}'s doc {check.doc} does not exist"
    elif not doc_text(path):
        message = f"{check.name}'s doc {check.doc} is empty"
    else:
        return []
    return [Finding(check.doc, 0, DANGLING, message)]
