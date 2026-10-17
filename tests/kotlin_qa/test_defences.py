"""Tests for listing the defences a configuration switches on."""

from pathlib import Path

from kotlin_qa.config import load_config
from kotlin_qa.defences import BUILTIN, active_defences

CONFIG = """\
[tools]
build = false

[[check]]
name = "spelling"
command = ["true"]
description = "Prose is in British English."
doc = "qa/spelling.md"
"""


def identifiers(root: Path) -> set[str]:
    return {defence.identifier for defence in active_defences(load_config(root))}


def test_every_lane_defence_is_listed_by_default(tmp_path: Path) -> None:
    found = identifiers(tmp_path)
    assert "kqaci.format" in found
    assert "kqaci.suppression.unrecorded" in found
    assert "kqaci.rules.untested" in found
    assert "kqaci.tests" in found


def test_a_switched_off_lane_lists_none_of_its_defences(tmp_path: Path) -> None:
    (tmp_path / "qa").mkdir()
    (tmp_path / "qa" / "kotlin-qa.toml").write_text(CONFIG, "utf-8")
    found = identifiers(tmp_path)
    assert "kqaci.build" not in found
    assert BUILTIN["kqaci.build"][0] == "build"


def test_project_checks_and_bundled_rules_are_listed_with_their_origin(tmp_path: Path) -> None:
    (tmp_path / "qa").mkdir()
    (tmp_path / "qa" / "kotlin-qa.toml").write_text(CONFIG, "utf-8")
    by_id = {d.identifier: d for d in active_defences(load_config(tmp_path))}
    assert (by_id["spelling"].tool, by_id["spelling"].origin) == ("check", "project")
    bundled = [d for d in by_id.values() if d.tool == "semgrep"]
    assert bundled
    assert {d.origin for d in bundled} == {"bundled"}


def test_the_documentation_command_is_the_offline_one() -> None:
    defence = next(iter(active_defences(load_config(Path("/nonexistent")))))
    assert defence.doc == f"kotlin-qa rule-doc {defence.identifier}"
