# Adopting kotlin-qa-ci

## 1. Install and configure

```bash
pip install git+https://github.com/LongTermSupport/kotlin-qa-ci@v0.2.0
kotlin-qa install-tools
mkdir -p qa/rules qa/defences
```

`qa/kotlin-qa.toml` (every key is optional):

```toml
docs_dir = "qa/defences"          # project documentation pages
rule_dirs = ["qa/rules"]          # project Semgrep rules, each beside its fixture
scan_exclude = []                 # each pattern needs a record exception

[detekt]
overrides = ["qa/detekt.yml"]     # changes to the shipped Detekt configuration, each with a reason

[coverage]
minimum_line = 0                  # percent; set it to today's figure and only ever raise it

[summary]
file = "CLAUDE.md"                # the agent summary region is written here

[gradle]
wrapper = "./gradlew"
test_task = "testDebugUnitTest"
lint_task = "lint"
build_task = "assembleDebug"
detekt_tasks = ["detektDebug", "detektDebugUnitTest"]
coverage_task = "createDebugUnitTestCoverageReport"
coverage_report = "app/build/reports/coverage/test/debug/report.xml"

[record]
max_total = 20
max_per_rule = 5
max_review_days = 180
```

Switching a lane off (`[tools] lint = false`) is itself reported as an unrecorded suppression.

## 2. Run it

```bash
kotlin-qa run             # formats in place, then everything else
kotlin-qa run --ci        # checks only; CI=true does the same
kotlin-qa rules           # what is enforced, and the record
```

The tools come from `kotlin-qa install-tools`, which pins each version and checks its SHA-256.

The Gradle lanes (`detekt`, `lint`, `test`, `coverage`, `build`) are run with
`-I kotlin-qa.init.gradle`, shipped in this package. It adds the pinned Detekt to each Kotlin
module, turns on unit test coverage for Android modules and makes Kotlin compiler warnings errors.
No build file changes. `qa/detekt.yml` is layered over the shipped configuration; a rule entry
that is anything other than `active: true` needs a comment directly above it saying why.

Rule fixtures are Kotlin files that ktlint checks, so name them in PascalCase (`NoSleep.kt` beside
`NoSleep.yml`).

## 3. Handle the first run

Expect findings. For each one the method asks the same question: is this an instance of a class
of defect? If so, write the rule first (see [adding-a-defence.md](adding-a-defence.md)), show it
fail on the instance, then fix the instance. If the finding is a deliberate exception, record it:

```toml
[[exception]]
rule = "ktlint::standard:no-wildcard-imports"
path = "app/src/main/kotlin/com/example/Generated.kt"
justification = "The generated file imports a whole package by design and is rewritten on each build."
decided_by = "alice"
decided_on = 2026-03-01
review_by = 2026-06-01
```

A finding of a Semgrep rule is covered the same way, with `covers = "findings"`:

```toml
[[exception]]
rule = "semgrep::kqaci.kt.empty-catch"
covers = "findings"
...
```

## 4. CI

Install Python 3.11+, `pip install git+https://github.com/LongTermSupport/kotlin-qa-ci@v<version>`,
run `kotlin-qa install-tools`, set up Java, and run `kotlin-qa run --ci`. Check out with
`fetch-depth: 0`, since the `leaks` lane reads the whole history. The reusable workflow in `.github/workflows/qa.yml` of this repository does
exactly that: call it with `uses: LongTermSupport/kotlin-qa-ci/.github/workflows/qa.yml@<tag>`.

## 5. Agents

`kotlin-qa summary` writes one standing instruction per defence between markers in the file named
by `[summary] file`. The `summary` lane fails when the region is stale.
