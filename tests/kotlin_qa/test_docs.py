"""Tests for resolving an identifier to documentation, offline, and the dangling-docs check."""

from pathlib import Path

from kotlin_qa.config import load_config
from kotlin_qa.defences import BUILTIN, Defence, active_defences
from kotlin_qa.docs import DANGLING, check_docs, missing_sections, resolve

PAGE = "# x\n\n## What it flags\n\na\n\n## Why\n\nb\n\n## How to fix correctly\n\nc\n"
CHECK = """\
[[check]]
name = "spelling"
command = ["true"]
description = "Prose is in British English."
doc = "qa/spelling.md"
"""


def project(tmp_path: Path, toml: str = "") -> Path:
    (tmp_path / "qa" / "defences").mkdir(parents=True)
    (tmp_path / "qa" / "kotlin-qa.toml").write_text(toml, "utf-8")
    return tmp_path


def test_every_builtin_identifier_has_a_complete_bundled_page() -> None:
    config = load_config(Path("/nonexistent"))
    for identifier in BUILTIN:
        page = resolve(identifier, config)
        assert page is not None, identifier
        assert missing_sections(page) == [], identifier


def test_every_bundled_rule_has_a_complete_bundled_page() -> None:
    config = load_config(Path("/nonexistent"))
    defences = [d for d in active_defences(config) if d.tool == "semgrep"]
    assert defences
    assert check_docs(config, defences) == []


def test_a_project_page_resolves_by_identifier(tmp_path: Path) -> None:
    root = project(tmp_path)
    (root / "qa" / "defences" / "proj.kt.no-sleep.md").write_text(PAGE, "utf-8")
    assert resolve("proj.kt.no-sleep", load_config(root)) == PAGE


def test_a_semgrep_identifier_resolves_with_or_without_its_tool_prefix(tmp_path: Path) -> None:
    config = load_config(Path("/nonexistent"))
    assert resolve("semgrep::kqaci.kt.empty-catch", config) == resolve(
        "kqaci.kt.empty-catch", config
    )


def test_a_project_check_resolves_to_its_description_and_doc(tmp_path: Path) -> None:
    root = project(tmp_path, CHECK)
    (root / "qa" / "spelling.md").write_text("Spelling rules live here.\n", "utf-8")
    page = resolve("spelling", load_config(root))
    assert page is not None
    assert "Prose is in British English." in page
    assert "Spelling rules live here." in page


def test_a_catalogue_identifier_resolves_to_a_route_page_naming_the_tool() -> None:
    config = load_config(Path("/nonexistent"))
    page = resolve("ktlint::standard:indent", config)
    assert page is not None
    assert "ktlint" in page
    assert "standard:indent" in page
    assert "kqaci.suppression.unrecorded" in page


def test_an_unknown_identifier_resolves_to_nothing() -> None:
    assert resolve("nonsense-without-a-home", load_config(Path("/nonexistent"))) is None


def test_a_project_defence_without_a_page_is_dangling(tmp_path: Path) -> None:
    root = project(tmp_path)
    found = check_docs(load_config(root), [Defence("proj.kt.x", "semgrep", "project", "s")])
    assert [(f.rule, f.path) for f in found] == [(DANGLING, "qa/defences/proj.kt.x.md")]


def test_a_page_missing_a_section_is_dangling(tmp_path: Path) -> None:
    root = project(tmp_path)
    (root / "qa" / "defences" / "proj.kt.x.md").write_text("# x\n\n## Why\n\nb\n", "utf-8")
    found = check_docs(load_config(root), [Defence("proj.kt.x", "semgrep", "project", "s")])
    assert len(found) == 1
    assert "What it flags" in found[0].message


def test_a_check_whose_doc_file_is_missing_is_dangling(tmp_path: Path) -> None:
    root = project(tmp_path, CHECK)
    config = load_config(root)
    found = check_docs(config, [Defence("spelling", "check", "project", "s")])
    assert [(f.rule, f.path) for f in found] == [(DANGLING, "qa/spelling.md")]
