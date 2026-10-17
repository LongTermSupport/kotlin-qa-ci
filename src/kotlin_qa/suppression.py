"""Every route that silences a detector, in source, resources and configuration, held to the record.

Kotlin and Java source is read with a small lexer, so a directive inside a string or a comment
that only quotes one is not a directive. Each site names the tool it silences and the identifiers
it names; a site that names none silences everything and can never be recorded.
"""

from __future__ import annotations

import os
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from kotlin_qa.config import CONFIG_FILE
from kotlin_qa.finding import Finding
from kotlin_qa.globs import match_any
from kotlin_qa.record import STALE, RecordEntry

if TYPE_CHECKING:
    from kotlin_qa.config import Config

UNRECORDED = "kqaci.suppression.unrecorded"
BLANKET = "kqaci.suppression.blanket"
UNSCANNED = "kqaci.suppression.unscanned"

SKIPPED_DIRECTORIES = frozenset(
    {".git", ".gradle", ".idea", ".kotlin", ".venv", "build", "node_modules", "__pycache__"}
)
SCANNED_SUFFIXES = (".kt", ".kts", ".java", ".xml", ".gradle")
EDITORCONFIG = ".editorconfig"


@dataclass(frozen=True)
class Site:
    """One place that silences a tool: the identifiers it names, or none for a blanket."""

    path: str
    line: int
    tool: str
    codes: tuple[str, ...]
    detail: str = ""

    @property
    def rule_ids(self) -> tuple[str, ...]:
        """Return the record identifiers this site needs, one per code."""
        return tuple(f"{self.tool}::{code}" for code in self.codes)


# --- the Kotlin and Java lexer ---------------------------------------------------------------


@dataclass(frozen=True)
class Scan:
    """What the lexer found: the comments, the string ranges, and the source minus comments."""

    comments: tuple[tuple[int, str], ...]
    strings: tuple[tuple[int, int], ...]
    code: str


@dataclass
class _OpenString:
    """A string literal being read: its kind, where it began, and its template brace depth."""

    raw: bool
    start: int
    braces: int = 0


def _line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def _blank(text: str) -> str:
    return "".join(ch if ch == "\n" else " " for ch in text)


def _block_comment_end(source: str, start: int) -> int:
    """Return the offset just past the (possibly nested) block comment that begins at start."""
    depth, end = 1, start + 2
    while end < len(source) and depth:
        if source.startswith("/*", end):
            depth += 1
            end += 2
        elif source.startswith("*/", end):
            depth -= 1
            end += 2
        else:
            end += 1
    return end


def _char_literal_end(source: str, start: int) -> int:
    """Return the offset just past the character literal that begins at start."""
    end = start + 1
    while end < len(source) and source[end] not in {"'", "\n"}:
        end += 2 if source[end] == "\\" else 1
    return min(end + 1, len(source))


def lex(source: str) -> Scan:
    """Find comments and string literals in Kotlin or Java source.

    Handles line and nested block comments, "..." and triple-quoted strings with ${...}
    templates, and character literals. Comments are blanked out of the returned code, which
    keeps every line where it was.
    """
    comments: list[tuple[int, str]] = []
    strings: list[tuple[int, int]] = []
    pieces: list[str] = []
    stack: list[_OpenString] = []
    length = len(source)
    index = 0
    while index < length:
        ch = source[index]
        top = stack[-1] if stack else None
        if top is not None and top.braces == 0:
            # Inside the text of a string literal.
            if ch == "\\" and not top.raw:
                pieces.append(source[index : index + 2])
                index += 2
            elif ch == "$" and source.startswith("{", index + 1):
                top.braces = 1
                pieces.append("${")
                index += 2
            elif not top.raw and ch == '"':
                strings.append((top.start, index + 1))
                stack.pop()
                pieces.append(ch)
                index += 1
            elif top.raw and source.startswith('"""', index):
                end = index + 3
                while end < length and source[end] == '"':
                    end += 1
                strings.append((top.start, end))
                stack.pop()
                pieces.append(source[index:end])
                index = end
            else:
                pieces.append(ch)
                index += 1
            continue
        # Code: at the top level, or inside a template.
        if source.startswith("//", index):
            end = source.find("\n", index)
            end = length if end == -1 else end
            comments.append((_line_of(source, index), source[index + 2 : end]))
            pieces.append(_blank(source[index:end]))
            index = end
        elif source.startswith("/*", index):
            end = _block_comment_end(source, index)
            comments.append((_line_of(source, index), source[index + 2 : max(index + 2, end - 2)]))
            pieces.append(_blank(source[index:end]))
            index = end
        elif source.startswith('"""', index):
            stack.append(_OpenString(raw=True, start=index))
            pieces.append('"""')
            index += 3
        elif ch == '"':
            stack.append(_OpenString(raw=False, start=index))
            pieces.append(ch)
            index += 1
        elif ch == "'":
            end = _char_literal_end(source, index)
            pieces.append(source[index:end])
            index = end
        else:
            if top is not None and ch == "{":
                top.braces += 1
            elif top is not None and ch == "}":
                top.braces -= 1
            pieces.append(ch)
            index += 1
    return Scan(tuple(comments), tuple(strings), "".join(pieces))


# --- Kotlin and Java source ------------------------------------------------------------------

_ANNOTATION = re.compile(
    r"@(?:(?:file|get|set|field|param|property|receiver|setparam|delegate):)?"
    r"(Suppress|SuppressWarnings|SuppressLint)\b"
)
_QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')
_KTLINT = re.compile(r"^\s*ktlint[-:]disable(?:-next-line|-line)?\b(.*)", re.DOTALL)
_NOINSPECTION = re.compile(r"^\s*noinspection\b(.*)", re.DOTALL)
_NOSEM = re.compile(r"^\s*nosem(?:grep)?\b(?:\s*:\s*(.*))?", re.DOTALL)
_WORDS = re.compile(r"[^\s,]+")


def _words(text: str | None) -> tuple[str, ...]:
    if not text:
        return ()
    return tuple(_WORDS.findall(text.replace("*/", " ")))


def _argument_end(code: str, start: int, strings: dict[int, int]) -> int:
    """Return the offset just past the parenthesis that closes the one at start."""
    depth, index = 0, start
    while index < len(code):
        if index in strings:
            index = strings[index]
            continue
        if code[index] == "(":
            depth += 1
        elif code[index] == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return len(code)


def _annotation_sites(display: str, scan: Scan) -> list[Site]:
    code = scan.code
    strings = dict(scan.strings)
    found: list[Site] = []
    for match in _ANNOTATION.finditer(code):
        if any(start <= match.start() < end for start, end in scan.strings):
            continue
        cursor = match.end()
        while cursor < len(code) and code[cursor] in " \t\r\n":
            cursor += 1
        names: list[str] = []
        if cursor < len(code) and code[cursor] == "(":
            end = _argument_end(code, cursor, strings)
            names = [m.group(1) for m in _QUOTED.finditer(code[cursor:end])]
        line = _line_of(code, match.start())
        found.extend(_annotation_to_sites(display, line, match.group(1), names))
    return found


def _annotation_to_sites(display: str, line: int, name: str, names: list[str]) -> list[Site]:
    if name == "SuppressLint":
        codes = tuple(n for n in names if n.lower() != "all")
        blanket = not names or len(codes) != len(names)
        return [Site(display, line, "lint", () if blanket else codes)]
    if not names:
        return [Site(display, line, "kotlin", ())]
    ktlint = tuple(n.removeprefix("ktlint:") for n in names if n.startswith("ktlint:"))
    others = tuple(n for n in names if not n.startswith("ktlint:"))
    sites = []
    if others:
        sites.append(Site(display, line, "kotlin", others))
    if ktlint:
        sites.append(Site(display, line, "ktlint", ktlint))
    return sites


def _comment_sites(display: str, scan: Scan) -> list[Site]:
    found: list[Site] = []
    for line, text in scan.comments:
        if match := _KTLINT.match(text):
            found.append(Site(display, line, "ktlint", _words(match.group(1))))
        elif match := _NOINSPECTION.match(text):
            found.append(Site(display, line, "idea", _words(match.group(1))))
        elif match := _NOSEM.match(text):
            found.append(Site(display, line, "semgrep", _words(match.group(1))))
    return found


def kotlin_sites(display: str, source: str) -> list[Site]:
    """Return every suppression annotation and directive comment in Kotlin or Java source."""
    scan = lex(source)
    return sorted(
        _annotation_sites(display, scan) + _comment_sites(display, scan),
        key=lambda site: (site.line, site.tool),
    )


# --- resources, Gradle and EditorConfig --------------------------------------------------------

_XML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_TOOLS_ATTR = re.compile(r'tools:(?:ignore|suppress)\s*=\s*"([^"]*)"')
_ISSUE_TAG = re.compile(r"<issue\b([^>]*)>", re.DOTALL)
_ATTR = re.compile(r'([\w:.-]+)\s*=\s*"([^"]*)"')


def xml_sites(display: str, source: str) -> list[Site]:
    """Return tools:ignore and tools:suppress attributes, lint.xml ignores and baseline files."""
    found: list[Site] = []
    name = PurePosixPath(display).name
    if name.startswith("lint-baseline") and name.endswith(".xml"):
        found.append(Site(display, 1, "lint", ("baseline",)))
    text = _XML_COMMENT.sub(lambda m: _blank(m.group(0)), source)
    for match in _TOOLS_ATTR.finditer(text):
        codes = _words(match.group(1))
        blanket = not codes or any(code.lower() == "all" for code in codes)
        found.append(Site(display, _line_of(text, match.start()), "lint", () if blanket else codes))
    if name == "lint.xml":
        for tag in _ISSUE_TAG.finditer(text):
            attributes = dict(_ATTR.findall(tag.group(1)))
            if attributes.get("severity") == "ignore":
                code = attributes.get("id")
                found.append(
                    Site(display, _line_of(text, tag.start()), "lint", (code,) if code else ())
                )
    return sorted(found, key=lambda site: site.line)


_GRADLE_FLAGS = (
    (re.compile(r"\babortOnError\s*=\s*false\b"), "lint", "abortOnError"),
    (re.compile(r"\bwarningsAsErrors\s*=\s*false\b"), "lint", "warningsAsErrors"),
    (re.compile(r"^\s*baseline\s*="), "lint", "baseline"),
    (re.compile(r"\bignoreWarnings\s*=\s*true\b"), "lint", "ignoreWarnings"),
    (re.compile(r"\bcheckReleaseBuilds\s*=\s*false\b"), "lint", "checkReleaseBuilds"),
    (re.compile(r"\bsuppressWarnings\s*=\s*true\b"), "kotlin", "suppressWarnings"),
)
_GRADLE_DISABLE = re.compile(r"\bdisable(?:\s*\+=|\.add\(|\.addAll\(|\()\s*(.*)")


def gradle_sites(display: str, source: str) -> list[Site]:
    """Return the Gradle settings that loosen Android Lint or the Kotlin compiler's warnings."""
    scan = lex(source)
    found: list[Site] = []
    if display.endswith(".kts"):
        found.extend(_annotation_sites(display, scan) + _comment_sites(display, scan))
    for number, line in enumerate(scan.code.splitlines(), start=1):
        for pattern, tool, code in _GRADLE_FLAGS:
            if pattern.search(line):
                found.append(Site(display, number, tool, (code,)))
        if match := _GRADLE_DISABLE.search(line):
            codes = tuple(m.group(1) for m in _QUOTED.finditer(match.group(1)))
            found.extend(Site(display, number, "lint", (code,)) for code in codes)
    return sorted(found, key=lambda site: site.line)


_EDITORCONFIG_RULE = re.compile(r"^\s*ktlint_([a-z]+)_([\w-]+)\s*=\s*disabled\b", re.IGNORECASE)
_EDITORCONFIG_SET = re.compile(r"^\s*ktlint_([a-z]+)\s*=\s*disabled\b", re.IGNORECASE)
_EDITORCONFIG_LIST = re.compile(r"^\s*(?:ktlint_)?disabled_rules\s*=\s*(.*)", re.IGNORECASE)


def editorconfig_sites(display: str, source: str) -> list[Site]:
    """Return the .editorconfig lines that disable ktlint rules."""
    found: list[Site] = []
    for number, line in enumerate(source.splitlines(), start=1):
        if match := _EDITORCONFIG_RULE.match(line):
            found.append(Site(display, number, "ktlint", (f"{match.group(1)}:{match.group(2)}",)))
        elif _EDITORCONFIG_SET.match(line):
            found.append(Site(display, number, "ktlint", ()))
        elif match := _EDITORCONFIG_LIST.match(line):
            found.append(Site(display, number, "ktlint", _words(match.group(1))))
    return found


def file_sites(root: Path, name: str) -> list[Site] | Finding:
    """Return the suppression sites in one project file, or a finding if it cannot be read."""
    try:
        source = (root / name).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as error:
        return Finding(name, 0, UNSCANNED, f"cannot be scanned: {error}")
    base = PurePosixPath(name).name
    if base == EDITORCONFIG:
        return editorconfig_sites(name, source)
    if base.endswith((".gradle.kts", ".gradle")):
        return gradle_sites(name, source)
    if base.endswith((".kt", ".kts", ".java")):
        return kotlin_sites(name, source)
    if base.endswith(".xml"):
        return xml_sites(name, source)
    return []


def config_sites(root: Path) -> list[Site]:
    """Return what the kotlin-qa configuration itself switches off or leaves out of the scan."""
    path = root / CONFIG_FILE
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    lines = text.splitlines()

    def find(needle: str) -> int:
        return next((n for n, line in enumerate(lines, 1) if needle in line), 1)

    found = [
        Site(CONFIG_FILE, find(f"{tool} ="), "kqa", (f"tools.{tool}",))
        for tool, state in data.get("tools", {}).items()
        if state is False
    ]
    found.extend(
        Site(CONFIG_FILE, find(pattern), "kqa", (f"scan_exclude:{pattern}",))
        for pattern in data.get("scan_exclude", [])
    )
    return found


# --- choosing files --------------------------------------------------------------------------


def within(name: str, path: str) -> bool:
    """Return True when the relative file name is path itself or lies below it."""
    prefix = path.rstrip("/")
    return prefix in {"", "."} or name == prefix or name.startswith(prefix + "/")


def _scanned(name: str) -> bool:
    base = PurePosixPath(name).name
    return base == EDITORCONFIG or base.endswith(SCANNED_SUFFIXES)


def _git_files(root: Path) -> list[str] | None:
    inside = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
    )
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return None
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        check=True,
    )
    return sorted({name for name in result.stdout.decode().split("\0") if name})


def project_files(root: Path, scan_exclude: tuple[str, ...]) -> list[str]:
    """Return the project's scanned files, relative and sorted, honouring .gitignore and excludes.

    Without git, every file outside Gradle's and the IDE's directories and build output.
    """
    listed = _git_files(root)
    if listed is None:
        listed = []
        for directory, subdirectories, files in os.walk(root):
            subdirectories[:] = [d for d in subdirectories if d not in SKIPPED_DIRECTORIES]
            base = Path(directory).relative_to(root)
            listed.extend((base / name).as_posix() for name in files)
    return sorted(
        name
        for name in listed
        if _scanned(name) and not match_any(scan_exclude, name) and (root / name).is_file()
    )


def scope_files(root: Path, scan_exclude: tuple[str, ...], paths: tuple[str, ...]) -> list[str]:
    """Return the project's scanned files under paths, listed one by one."""
    return [
        name
        for name in project_files(root, scan_exclude)
        if any(within(name, path) for path in paths)
    ]


# --- holding sites to the record ---------------------------------------------------------------


def suppression_findings(
    config: Config, entries: list[RecordEntry], paths: tuple[str, ...] | None
) -> list[Finding]:
    """Scan the project, or only paths, and hold every suppression to the record.

    The configuration's own switches and stale entries are checked only on a full scan, since a
    subset cannot tell an entry that covers nothing from one covering a file outside the subset.
    """
    root = config.root
    files = (
        project_files(root, config.scan_exclude)
        if paths is None
        else scope_files(root, config.scan_exclude, paths)
    )
    sites: list[Site] = [] if paths is not None else config_sites(root)
    findings: list[Finding] = []
    for name in files:
        found = file_sites(root, name)
        if isinstance(found, Finding):
            findings.append(found)
        else:
            sites.extend(found)
    return findings + check_suppressions(
        sites, entries, full_scan=paths is None, record_path=config.record.path
    )


def check_suppressions(
    sites: list[Site],
    entries: list[RecordEntry],
    *,
    full_scan: bool,
    record_path: str = "qa/record.toml",
) -> list[Finding]:
    """Hold every site to the record; on a full scan, report entries that cover nothing."""
    findings: list[Finding] = []
    entries = [entry for entry in entries if entry.covers == "site"]
    recorded = {(entry.rule, entry.path) for entry in entries}
    used: set[tuple[str, str]] = set()
    for site in sites:
        if not site.codes:
            findings.append(
                Finding(
                    site.path,
                    site.line,
                    BLANKET,
                    f"{site.tool} is silenced here for every identifier; name the identifier and "
                    "record the exception",
                )
            )
            continue
        for rule in site.rule_ids:
            if (rule, site.path) in recorded:
                used.add((rule, site.path))
                continue
            findings.append(
                Finding(
                    site.path,
                    site.line,
                    UNRECORDED,
                    f"{rule} is suppressed here with no exception in the project record",
                )
            )
    if full_scan:
        findings.extend(
            Finding(
                record_path,
                entry.line,
                STALE,
                f"exception #{entry.number} ({entry.rule}, {entry.path}) covers no suppression; "
                "remove it",
            )
            for entry in entries
            if (entry.rule, entry.path) not in used
        )
    return findings
