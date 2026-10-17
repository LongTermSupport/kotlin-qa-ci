# Changelog

## 0.1.1

- The Semgrep lane no longer scans the rules' own fixtures, whose red lines are meant to fire.

## 0.1.0

First release.

- Lanes: ktlint format, record, suppression scan, agent summary, documentation, rule proof,
  Semgrep, Android Lint, unit tests, build; project checks as extra lanes.
- Four bundled Semgrep rules, each with a fixture and a documentation page.
- The project record with `covers = "site" | "findings"`.
- Offline `rule-doc` for every identifier the tool prints.
- `kotlin-qa rule`: one rule alone on given paths.
