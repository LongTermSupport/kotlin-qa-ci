"""Tests for finding every route that silences a detector, and holding each to the record."""

from datetime import date
from pathlib import Path

from kotlin_qa.config import load_config
from kotlin_qa.record import RecordEntry
from kotlin_qa.suppression import (
    BLANKET,
    UNRECORDED,
    Site,
    check_suppressions,
    editorconfig_sites,
    file_sites,
    gradle_sites,
    kotlin_sites,
    project_files,
    suppression_findings,
    xml_sites,
)


def sites(source: str) -> list[tuple[int, str, tuple[str, ...]]]:
    return [(s.line, s.tool, s.codes) for s in kotlin_sites("A.kt", source)]


def test_suppress_annotation_names_what_it_silences() -> None:
    source = '@Suppress("UNCHECKED_CAST", "unused")\nfun a() = Unit\n'
    assert sites(source) == [(1, "kotlin", ("UNCHECKED_CAST", "unused"))]


def test_file_and_use_site_targets_are_found() -> None:
    source = '@file:Suppress("MagicNumber")\nclass A(@get:Suppress("x") val b: Int)\n'
    assert sites(source) == [(1, "kotlin", ("MagicNumber",)), (2, "kotlin", ("x",))]


def test_suppress_with_named_array_argument() -> None:
    assert sites('@Suppress(names = ["a", "b"])\nfun f() {}\n') == [(1, "kotlin", ("a", "b"))]


def test_suppress_without_names_is_a_blanket() -> None:
    assert sites("@Suppress()\nfun f() {}\n") == [(1, "kotlin", ())]


def test_an_argument_split_over_lines_is_one_site_at_its_first_line() -> None:
    source = '@Suppress(\n    "a",\n    "b",\n)\nfun f() {}\n'
    assert sites(source) == [(1, "kotlin", ("a", "b"))]


def test_suppress_lint_belongs_to_android_lint_and_all_is_a_blanket() -> None:
    assert sites('@SuppressLint("HardcodedText")\nfun f() {}\n') == [
        (1, "lint", ("HardcodedText",))
    ]
    assert sites('@SuppressLint("all")\nfun f() {}\n') == [(1, "lint", ())]


def test_java_suppress_warnings_is_found() -> None:
    assert sites('@SuppressWarnings("unchecked")\nvoid f() {}\n') == [(1, "kotlin", ("unchecked",))]


def test_a_ktlint_rule_inside_suppress_belongs_to_ktlint() -> None:
    source = '@Suppress("ktlint:standard:no-wildcard-imports")\nfun f() {}\n'
    assert sites(source) == [(1, "ktlint", ("standard:no-wildcard-imports",))]


def test_ktlint_disable_comments_are_found_in_each_spelling() -> None:
    source = (
        "val a = 1 // ktlint-disable no-semi\n"
        "/* ktlint-disable max-line-length */\n"
        "// ktlint-disable-next-line\n"
        "// ktlint:disable standard:indent\n"
    )
    assert sites(source) == [
        (1, "ktlint", ("no-semi",)),
        (2, "ktlint", ("max-line-length",)),
        (3, "ktlint", ()),
        (4, "ktlint", ("standard:indent",)),
    ]


def test_noinspection_and_nosem_comments_are_found() -> None:
    source = "// noinspection UnusedDeclaration, unused\n// nosem: KQA-X\n// nosemgrep\n"
    assert sites(source) == [
        (1, "idea", ("UnusedDeclaration", "unused")),
        (2, "semgrep", ("KQA-X",)),
        (3, "semgrep", ()),
    ]


def test_a_directive_inside_a_string_is_not_one() -> None:
    source = (
        'val a = "@Suppress(\\"x\\") // noinspection y"\n'
        'val b = """\n@SuppressLint("z")\n// ktlint-disable\n"""\n'
        'val c = "${"@Suppress(\\"q\\")"}"\n'
    )
    assert sites(source) == []


def test_a_directive_inside_a_block_comment_that_quotes_it_is_only_a_comment() -> None:
    assert sites('/* the old way was @Suppress("x") */\nval a = 1\n') == []


def test_a_real_directive_after_a_string_with_a_comment_marker_is_still_found() -> None:
    source = 'val url = "http://example.com" // ktlint-disable max-line-length\n'
    assert sites(source) == [(1, "ktlint", ("max-line-length",))]


def test_nested_block_comments_and_char_literals_do_not_confuse_the_scan() -> None:
    source = "/* a /* b */ still comment */\nval c = '\"'\n@Suppress(\"x\")\nfun f() {}\n"
    assert sites(source) == [(3, "kotlin", ("x",))]


def test_a_string_template_with_braces_is_scanned_through() -> None:
    source = 'val s = "a ${mapOf("k" to "}")} b"\n@Suppress("x")\nfun f() {}\n'
    assert sites(source) == [(2, "kotlin", ("x",))]


def test_xml_tools_ignore_and_suppress_are_found() -> None:
    source = (
        '<TextView\n    tools:ignore="HardcodedText,ContentDescription"\n'
        '    tools:suppress="x" />\n<!-- tools:ignore="y" -->\n'
    )
    found = [(s.line, s.tool, s.codes) for s in xml_sites("res/a.xml", source)]
    assert found == [
        (2, "lint", ("HardcodedText", "ContentDescription")),
        (3, "lint", ("x",)),
    ]


def test_xml_ignore_all_is_a_blanket() -> None:
    assert [s.codes for s in xml_sites("a.xml", '<a tools:ignore="all"/>')] == [()]


def test_a_lint_baseline_file_is_a_suppression_route() -> None:
    found = xml_sites("app/lint-baseline.xml", "<issues/>")
    assert [(s.line, s.tool, s.codes) for s in found] == [(1, "lint", ("baseline",))]


def test_lint_xml_issues_set_to_ignore_are_found() -> None:
    source = '<lint>\n  <issue id="Foo" severity="ignore"/>\n  <issue id="Bar" severity="error"/>\n</lint>'
    assert [(s.line, s.codes) for s in xml_sites("lint.xml", source)] == [(2, ("Foo",))]


def test_gradle_lint_settings_that_loosen_the_check_are_found() -> None:
    source = (
        "android {\n  lint {\n    abortOnError = false\n    warningsAsErrors = false\n"
        '    baseline = file("lint-baseline.xml")\n    disable += "A"\n    disable.add("B")\n'
        "    ignoreWarnings = true\n    checkReleaseBuilds = false\n  }\n}\n"
    )
    found = [(s.line, s.codes) for s in gradle_sites("app/build.gradle.kts", source)]
    assert found == [
        (3, ("abortOnError",)),
        (4, ("warningsAsErrors",)),
        (5, ("baseline",)),
        (6, ("A",)),
        (7, ("B",)),
        (8, ("ignoreWarnings",)),
        (9, ("checkReleaseBuilds",)),
    ]


def test_gradle_settings_that_tighten_or_do_nothing_are_not_routes() -> None:
    source = "lint {\n  abortOnError = true\n  warningsAsErrors = true\n}\nval baseline = 3\n"
    assert gradle_sites("build.gradle.kts", source) == []


def test_kotlin_suppress_warnings_in_gradle_is_found() -> None:
    found = gradle_sites("build.gradle.kts", "kotlinOptions {\n  suppressWarnings = true\n}\n")
    assert [(s.tool, s.codes) for s in found] == [("kotlin", ("suppressWarnings",))]


def test_editorconfig_disabling_a_ktlint_rule_is_found() -> None:
    source = (
        "[*.{kt,kts}]\nktlint_standard_no-wildcard-imports = disabled\n"
        "ktlint_standard_indent = enabled\nktlint_disabled_rules = a, b\n"
    )
    assert [(s.line, s.codes) for s in editorconfig_sites(".editorconfig", source)] == [
        (2, ("standard:no-wildcard-imports",)),
        (4, ("a", "b")),
    ]


def test_the_file_scan_dispatches_on_the_file_name(tmp_path: Path) -> None:
    (tmp_path / "A.kt").write_text('@Suppress("x")\nclass A\n', "utf-8")
    (tmp_path / "res").mkdir()
    (tmp_path / "res" / "a.xml").write_text('<a tools:ignore="y"/>', "utf-8")
    (tmp_path / ".editorconfig").write_text("ktlint_standard_x = disabled\n", "utf-8")
    assert [s.codes for s in file_sites(tmp_path, "A.kt")] == [("x",)]
    assert [s.codes for s in file_sites(tmp_path, "res/a.xml")] == [("y",)]
    assert [s.codes for s in file_sites(tmp_path, ".editorconfig")] == [("standard:x",)]


def test_an_unreadable_file_is_reported_not_skipped(tmp_path: Path) -> None:
    (tmp_path / "A.kt").write_bytes(b"\xff\xfe\x00bad")
    found = file_sites(tmp_path, "A.kt")
    assert not isinstance(found, list)
    assert found.rule == "kqaci.suppression.unscanned"


def entry(rule: str, path: str, number: int = 1) -> RecordEntry:
    return RecordEntry(number, rule, path, "j", "alice", date(2026, 1, 1), date(2026, 2, 1), 3)


def test_a_site_with_no_record_entry_is_unrecorded() -> None:
    found = check_suppressions(
        [Site("A.kt", 4, "kotlin", ("x",))], [], full_scan=True, record_path="qa/record.toml"
    )
    assert [(f.path, f.line, f.rule) for f in found] == [("A.kt", 4, UNRECORDED)]
    assert "kotlin::x" in found[0].message


def test_a_recorded_site_passes() -> None:
    found = check_suppressions(
        [Site("A.kt", 4, "kotlin", ("x",))],
        [entry("kotlin::x", "A.kt")],
        full_scan=True,
    )
    assert found == []


def test_a_blanket_site_can_never_be_recorded() -> None:
    found = check_suppressions(
        [Site("A.kt", 4, "ktlint", ())], [entry("ktlint::all", "A.kt")], full_scan=False
    )
    assert [f.rule for f in found] == [BLANKET]


def test_a_record_entry_covering_nothing_is_stale_on_a_full_scan_only() -> None:
    stale = [entry("kotlin::x", "A.kt")]
    full = check_suppressions([], stale, full_scan=True, record_path="qa/record.toml")
    assert [f.rule for f in full] == ["kqaci.record.stale"]
    assert full[0].path == "qa/record.toml"
    assert check_suppressions([], stale, full_scan=False) == []


def make_project(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "A.kt").write_text('@Suppress("x")\nclass A\n', "utf-8")
    (tmp_path / "app" / "build").mkdir()
    (tmp_path / "app" / "build" / "G.kt").write_text('@Suppress("generated")\n', "utf-8")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "V.kt").write_text('@Suppress("vendored")\n', "utf-8")
    return tmp_path


def test_the_project_scan_skips_build_output_and_excluded_paths(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    assert project_files(root, ()) == ["app/A.kt", "vendor/V.kt"]
    assert project_files(root, ("vendor/**",)) == ["app/A.kt"]


def test_the_project_scan_holds_a_whole_project_to_the_record(tmp_path: Path) -> None:
    config = load_config(make_project(tmp_path))
    found = suppression_findings(config, [], None)
    assert sorted((f.path, f.rule) for f in found) == [
        ("app/A.kt", UNRECORDED),
        ("vendor/V.kt", UNRECORDED),
    ]
    only = suppression_findings(config, [], ("app",))
    assert [f.path for f in only] == ["app/A.kt"]
