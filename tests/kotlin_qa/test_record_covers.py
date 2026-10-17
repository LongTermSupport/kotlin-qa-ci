"""Tests for exceptions that cover a detector's findings rather than a suppression in source."""

from datetime import date
from pathlib import Path

from kotlin_qa.record import load_record

GOOD = (
    "The upload worker waits on this call inside a bounded run, so a hang is cut off by the "
    "operating system and never reaches the user."
)
TODAY = date(2026, 3, 1)


def entry(rule: str, **extra: str) -> str:
    fields = {
        "rule": f'"{rule}"',
        "path": '"app/src/main/kotlin/A.kt"',
        "justification": f'"{GOOD}"',
        "decided_by": '"alice"',
        "decided_on": "2026-01-15",
        "review_by": "2026-04-15",
    }
    fields.update(extra)
    return "[[exception]]\n" + "\n".join(f"{k} = {v}" for k, v in fields.items()) + "\n"


def load(tmp_path: Path, text: str) -> tuple[list, list[str]]:
    path = tmp_path / "record.toml"
    path.write_text(text, encoding="utf-8")
    entries, findings = load_record(path, "qa/record.toml", today=TODAY)
    return entries, [finding.render() for finding in findings]


def test_an_exception_covers_a_suppression_site_unless_it_says_otherwise(tmp_path: Path) -> None:
    entries, findings = load(tmp_path, entry("kotlin::unused"))
    assert findings == []
    assert entries[0].covers == "site"


def test_an_exception_may_cover_findings_of_a_semgrep_rule(tmp_path: Path) -> None:
    entries, findings = load(tmp_path, entry("semgrep::kqaci.kt.x", covers='"findings"'))
    assert findings == []
    assert entries[0].covers == "findings"


def test_findings_can_be_covered_only_for_semgrep(tmp_path: Path) -> None:
    entries, findings = load(tmp_path, entry("kotlin::unused", covers='"findings"'))
    assert entries == []
    assert any("covers = \"findings\" is only for semgrep" in line for line in findings)


def test_covers_must_be_site_or_findings(tmp_path: Path) -> None:
    entries, findings = load(tmp_path, entry("semgrep::x", covers='"everything"'))
    assert entries == []
    assert any("covers must be" in line for line in findings)
