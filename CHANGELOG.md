# Changelog

## 0.2.0

New lanes, all blocking, each with a documented identifier:

- `detekt`: Detekt 2.0.0-alpha.6 with type information, run through a Gradle init script this
  package ships, so the project's build files need no change. A strict default configuration is
  shipped; the project's `qa/detekt.yml` is layered over it and `kqaci.detekt.unjustified` fails
  any loosening without a reason in a comment directly above it.
- `coverage`: JaCoCo line coverage against `[coverage] minimum_line` (`kqaci.coverage.below`).
- `shell` (ShellCheck), `workflows` (actionlint and zizmor), `leaks` (gitleaks over the history).
- Kotlin compiler warnings are errors in the `test`, `build` and `lint` Gradle runs.
- `kotlin-qa install-tools` downloads checksum-pinned ktlint, ShellCheck, actionlint, zizmor and
  gitleaks. A tool resolves from its environment variable, the cache, then the search path.
- Suppression routes added: Detekt (`@Suppress("detekt:...")`, a baseline file, `ignoreFailures`),
  `allWarningsAsErrors = false`, `# shellcheck disable=`, `gitleaks:allow`, `.gitleaksignore`,
  `zizmor: ignore`, and `ignore:` in the actionlint and zizmor configuration.

Fixed, found by adopting it in the Speech Recorder app:

- A `scan_exclude` glob could never be recorded, because the record's rule pattern rejected `/`
  and `*`; the tool required an exception that could not be written.

Changed: the reusable workflow no longer takes ktlint inputs; it runs `install-tools`.

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
