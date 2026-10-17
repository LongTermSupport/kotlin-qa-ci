# kotlin-qa-ci

One QA entry point for Kotlin and Android projects, built for the
[Defence Before Fix](https://defence-before-fix.github.io/) (DBF) method. Run `kotlin-qa run`
locally and in CI and you get the same verdict: format, then every detector, then the tests and
the build, stopping before anything slow if a detector fails.

It is the Kotlin sibling of `py-qa-ci` and `rust-qa-ci`, and follows the same layout, record
format and identifier scheme.

## What it runs

| Lane          | What it does                                                               | Tool                  |
| ------------- | -------------------------------------------------------------------------- | --------------------- |
| `fmt`         | Formats Kotlin (checks only with `--ci`)                                   | ktlint                |
| `record`      | Validates `qa/record.toml`: person, dates, specific justification, budget  | kotlin-qa             |
| `suppression` | Finds every route that silences a tool and holds it to the record          | kotlin-qa             |
| `summary`     | Checks the generated agent summary is current                              | kotlin-qa             |
| `docs`        | Every listed identifier resolves to a complete documentation page          | kotlin-qa             |
| `rules`       | Every custom rule is named, has a fixture, and flags exactly its red lines | kotlin-qa and Semgrep |
| `semgrep`     | Runs the bundled and project rules over the project                        | Semgrep (pinned)      |
| `shell`       | Tracked `.sh` and `.bash` scripts                                          | ShellCheck (pinned)   |
| `workflows`   | GitHub Actions workflows: mistakes, then insecure patterns                 | actionlint, zizmor    |
| `leaks`       | Credentials anywhere in the commit history                                 | gitleaks (pinned)     |
| `detekt`      | Static analysis with type information, strict shipped configuration        | Detekt (pinned)       |
| _checks_      | Any command the project registers as a detector or runner                  | the project's own     |
| `lint`        | Android Lint (a detector, last because it compiles)                        | Gradle                |
| `test`        | Unit tests, with every Kotlin compiler warning an error                    | Gradle                |
| `coverage`    | Line coverage held to the project's minimum                                | Gradle and JaCoCo     |
| `build`       | The app builds, with every Kotlin compiler warning an error                | Gradle                |

The library owns the tools, their versions and their default configuration, as `php-qa-ci` does
for PHP. The Gradle lanes load an init script shipped here, so Detekt, coverage and
warnings-as-errors need no change to the project's build files. A project overrides the shipped
Detekt configuration in `qa/detekt.yml`, and each override needs its reason written on the line
above it.

Every failing line prints a stable identifier. `kotlin-qa rule-doc <identifier>` prints its
documentation offline, including a "How to fix correctly" section.

## Install

```bash
pip install git+https://github.com/LongTermSupport/kotlin-qa-ci@v0.2.0
kotlin-qa install-tools           # ktlint, ShellCheck, actionlint, zizmor, gitleaks, checksum-pinned
kotlin-qa tools                   # every lane and what runs it
```

Each tool is found from its environment variable (`KTLINT`, `SHELLCHECK`, `ACTIONLINT`, `ZIZMOR`,
`GITLEAKS`), else the copy `install-tools` put in `~/.cache/kotlin-qa` (or `$KOTLIN_QA_HOME`),
else the search path. `install-tools` refuses a download whose SHA-256 differs from the pin.
Pinned builds exist for Linux x86_64 and aarch64; elsewhere install the tool yourself. The
project needs a Gradle wrapper and Java. See
[docs/adopting.md](docs/adopting.md) for adding it to a project and to CI.

## Commands

```text
kotlin-qa run [-t LANE] [--skip LANE] [-p PATH] [--ci] [--fail-fast] [--json FILE]
kotlin-qa rules [--json]       every active defence and the project record
kotlin-qa rule-doc ID          documentation for any identifier a finding prints
kotlin-qa rule ID PATH...      one rule alone: exit 0 did not fire, 1 fired, 2 could not run
kotlin-qa docs-check           fail if a listed identifier has no documentation
kotlin-qa record check|list    validate or list the exceptions
kotlin-qa summary [--check]    write or check the agent summary region
kotlin-qa tools                every lane, whether it is on, and its tool
kotlin-qa install-tools [NAME] download the pinned tools into the cache
```

`kotlin-qa rule` is the red-before-green harness: run a new rule on its fixture and it exits 1,
which is the failing example the method asks to see before a fix.

## Bundled rules

| Identifier                     | Flags                                        |
| ------------------------------ | -------------------------------------------- |
| `kqaci.kt.await-no-timeout`    | `Tasks.await(task)` with no timeout          |
| `kqaci.kt.wakelock-no-timeout` | `WakeLock.acquire()` with no timeout         |
| `kqaci.kt.global-scope`        | `GlobalScope.launch` and `GlobalScope.async` |
| `kqaci.kt.empty-catch`         | A `catch` block with no statements           |

Projects add their own as Semgrep rule files under `qa/rules/`, each beside a fixture of the same
name. [docs/adding-a-defence.md](docs/adding-a-defence.md) walks through it.

## Exceptions

A suppression comment, a `tools:ignore`, a Lint baseline, a disabled ktlint rule: each is a hole
in the net, so each needs an entry in `qa/record.toml` naming the rule, the one file, who decided,
when, and a specific justification. Generic text is rejected, the record has a budget, and every
entry has a review date. An entry that covers nothing is itself a failure.

Semgrep's own `nosemgrep` comments and `.semgrepignore` are not honoured. The only way to cover a
Semgrep finding is a record entry with `covers = "findings"`.

## Conformance

The tool's own conformance statement, with its gaps, is in
[docs/CONFORMANCE.md](docs/CONFORMANCE.md).

## Licence

MIT.
