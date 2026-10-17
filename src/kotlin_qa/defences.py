"""Every defence active in a project, derived from the configuration in force, run by none."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from kotlin_qa.rules import load_rules

if TYPE_CHECKING:
    from kotlin_qa.config import Config

# kotlin-qa's own detectors and lane failures: identifier -> (lane that reports it, summary).
BUILTIN = {
    "kqaci.format": ("fmt", "Code is formatted by ktlint."),
    "kqaci.record.invalid": (
        "record",
        "Every record exception names one file, a person, dates and a specific justification.",
    ),
    "kqaci.record.budget": ("record", "The record stays within its total and per-rule budget."),
    "kqaci.record.expired": ("record", "No record exception is past its review_by date."),
    "kqaci.record.stale": ("suppression", "Every record exception covers a suppression."),
    "kqaci.suppression.unrecorded": (
        "suppression",
        "Every suppression comment or setting has a matching record exception.",
    ),
    "kqaci.suppression.blanket": (
        "suppression",
        "No suppression silences a tool without naming the identifier.",
    ),
    "kqaci.suppression.unscanned": (
        "suppression",
        "Every source file can be read, so its suppressions can be checked.",
    ),
    "kqaci.summary.stale": ("summary", "The generated agent summary matches the configuration."),
    "kqaci.docs.dangling": ("docs", "Every listed identifier resolves to documentation."),
    "kqaci.rules.invalid": ("rules", "Every custom rule file parses and is complete."),
    "kqaci.rules.unnamed": ("rules", "Every custom rule names its hazard and points at its docs."),
    "kqaci.rules.untested": (
        "rules",
        "Every custom rule has a fixture with a red example it flags and a green one it leaves.",
    ),
    "kqaci.rules.unproved": (
        "rules",
        "Every custom rule flags its red examples and nothing else in its fixture.",
    ),
    "kqaci.semgrep.error": (
        "semgrep",
        "Semgrep reads every source file completely, so no rule is skipped silently.",
    ),
    "kqaci.lint": ("lint", "Android Lint reports no issue."),
    "kqaci.tests": ("test", "The unit test suite passes."),
    "kqaci.build": ("build", "The app builds."),
}


@dataclass(frozen=True)
class Defence:
    """One active defence: the identifier it prints, who supplies it, and what it requires."""

    identifier: str
    tool: str
    origin: str
    summary: str

    @property
    def doc(self) -> str:
        """Return the command that prints this defence's documentation, offline."""
        return f"kotlin-qa rule-doc {self.identifier}"


def active_defences(config: Config) -> list[Defence]:
    """Return every defence the configuration switches on, without running any of them."""
    defences = [
        Defence(identifier, "kotlin-qa", "bundled", summary)
        for identifier, (lane, summary) in BUILTIN.items()
        if config.tools[lane] and (lane != "summary" or config.summary_file)
    ]
    if config.tools["semgrep"]:
        rules, _ = load_rules(config)
        defences.extend(Defence(r.identifier, "semgrep", r.origin, r.hazard) for r in rules)
    defences.extend(
        Defence(check.name, "check", "project", check.description) for check in config.checks
    )
    return defences
