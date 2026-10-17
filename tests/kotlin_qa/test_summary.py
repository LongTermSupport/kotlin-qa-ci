"""Tests for the agent summary region: generation, delivery and the staleness check."""

from datetime import date
from pathlib import Path

from kotlin_qa.config import load_config
from kotlin_qa.defences import Defence
from kotlin_qa.record import RecordEntry
from kotlin_qa.summary import BEGIN, END, check_summary, place, render, write_summary

DEFENCES = [
    Defence("kqaci.tests", "kotlin-qa", "bundled", "The test suite passes."),
    Defence("kqaci.kt.no-sleep", "semgrep", "bundled", "A sleeping worker holds its thread."),
    Defence("proj.kt.no-eval", "semgrep", "project", "Do not evaluate strings."),
    Defence("spelling", "check", "project", "Prose is in British English."),
]
ENTRY = RecordEntry(
    1, "ktlint::standard:indent", "A.kt", "x" * 50, "alice", date(2026, 1, 1), date(2026, 2, 1)
)


def summary_config(tmp_path: Path):
    (tmp_path / "qa").mkdir()
    (tmp_path / "qa" / "kotlin-qa.toml").write_text('[summary]\nfile = "AGENTS.md"\n', "utf-8")
    return load_config(tmp_path)


def test_render_lists_every_bespoke_defence_with_its_source_and_docs(tmp_path: Path) -> None:
    region = render(DEFENCES, [ENTRY], load_config(tmp_path))
    lines = region.splitlines()
    assert lines[0] == BEGIN
    assert lines[-1] == END
    assert "- `kqaci.tests` (kotlin-qa): The test suite passes. Docs: " in region
    assert "- `kqaci.kt.no-sleep` (Semgrep, bundled): A sleeping worker holds its thread." in region
    assert "`kotlin-qa rule-doc kqaci.kt.no-sleep`" in region
    assert "- `proj.kt.no-eval` (Semgrep, project): Do not evaluate strings." in region
    assert "- `spelling` (project check): Prose is in British English. Docs: " in region
    assert "ktlint's rules and Android Lint's checks also block" in region
    assert "1 exception in `qa/record.toml`" in region


def test_place_replaces_an_existing_region_and_keeps_the_rest() -> None:
    old = f"# Agents\n\nIntro.\n\n{BEGIN}\nold\n{END}\n\nAfter.\n"
    assert (
        place(old, f"{BEGIN}\nnew\n{END}")
        == f"# Agents\n\nIntro.\n\n{BEGIN}\nnew\n{END}\n\nAfter.\n"
    )


def test_place_appends_when_there_is_no_region() -> None:
    assert place("# Agents\n", f"{BEGIN}\nnew\n{END}") == f"# Agents\n\n{BEGIN}\nnew\n{END}\n"
    assert place("", f"{BEGIN}\nnew\n{END}") == f"{BEGIN}\nnew\n{END}\n"


def test_write_then_check_is_clean_and_drift_is_reported(tmp_path: Path) -> None:
    config = summary_config(tmp_path)
    assert [f.rule for f in check_summary(config, DEFENCES, [])] == ["kqaci.summary.stale"]
    write_summary(config, DEFENCES, [])
    assert check_summary(config, DEFENCES, []) == []
    assert [f.rule for f in check_summary(config, DEFENCES[:1], [])] == ["kqaci.summary.stale"]


def test_no_summary_file_configured_is_nothing_to_check(tmp_path: Path) -> None:
    assert check_summary(load_config(tmp_path), DEFENCES, []) == []
