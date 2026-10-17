"""Line coverage from the JaCoCo XML report, against the project's minimum."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from kotlin_qa.finding import Finding

if TYPE_CHECKING:
    from pathlib import Path

    from kotlin_qa.config import Config

IDENTIFIER = "kqaci.coverage.below"
_PERCENT = 100.0
_LINE_COUNTER = re.compile(r'<counter type="LINE" missed="(\d+)" covered="(\d+)"\s*/>')


def line_coverage(report: Path) -> float:
    """Return the report's total line coverage as a percentage.

    JaCoCo writes a LINE counter for each package and class and, last in the file, one for the
    whole report, so the total is the final LINE counter. The text is matched rather than parsed
    as XML: the report is the build's own output, and a regular expression needs no XML parser
    that could be sent an entity bomb.
    """
    counters = _LINE_COUNTER.findall(report.read_text(encoding="utf-8"))
    if not counters:
        msg = f"{report}: no LINE counter"
        raise ValueError(msg)
    missed, covered = (int(number) for number in counters[-1])
    total = missed + covered
    return _PERCENT * covered / total if total else _PERCENT


def check_coverage(config: Config) -> tuple[float | None, list[Finding]]:
    """Return the measured line coverage, or None, and a finding if it is missing or too low."""
    display = config.gradle.coverage_report
    report = config.root / display
    if not report.is_file():
        message = f"no coverage report at {display}; the coverage task did not write one"
        return None, [Finding(display, 0, IDENTIFIER, message)]
    try:
        figure = line_coverage(report)
    except (OSError, ValueError) as error:
        return None, [Finding(display, 0, IDENTIFIER, f"cannot read the coverage report: {error}")]
    minimum = config.coverage_minimum
    if figure < minimum:
        message = f"line coverage is {figure:.1f}%, below the minimum of {minimum:g}%"
        return figure, [Finding(display, 0, IDENTIFIER, message)]
    return figure, []
