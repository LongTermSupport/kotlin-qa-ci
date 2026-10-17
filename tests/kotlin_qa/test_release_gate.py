"""The release gate: nothing ships as a defence unless it is documented and proved."""

from pathlib import Path

from kotlin_qa.config import load_config
from kotlin_qa.defences import BUILTIN, active_defences
from kotlin_qa.docs import BUNDLED_DOCS, check_docs
from kotlin_qa.pipeline import _LANE_IDENTIFIERS
from kotlin_qa.rules import BUNDLED_RULES, load_rules
from kotlin_qa.semgrep_run import prove_rules

NOWHERE = Path("/nonexistent")


def test_every_bundled_rule_is_complete_and_has_a_fixture_with_red_and_green() -> None:
    rules, findings = load_rules(load_config(NOWHERE))
    assert findings == []
    assert {rule.file.stem for rule in rules} == {p.stem for p in BUNDLED_RULES.glob("*.yml")}


def test_every_bundled_rule_flags_its_red_lines_and_leaves_its_green_ones() -> None:
    assert prove_rules(load_config(NOWHERE)) == []


def test_every_active_defence_has_a_complete_documentation_page() -> None:
    config = load_config(NOWHERE)
    assert check_docs(config, active_defences(config)) == []


def test_no_documentation_page_is_orphaned() -> None:
    config = load_config(NOWHERE)
    known = {d.identifier for d in active_defences(config)} | set(BUILTIN)
    pages = {page.stem for page in BUNDLED_DOCS.glob("*.md")}
    assert pages - known == set()


def test_every_lane_failure_message_names_a_defence_that_exists() -> None:
    assert set(_LANE_IDENTIFIERS.values()) <= set(BUILTIN)
