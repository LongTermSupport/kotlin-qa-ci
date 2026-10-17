# Adding a defence

A defence is a rule, a fixture that proves it, and a page that explains it. In that order.

## 1. Write the fixture first

`qa/rules/no-sleep.kt`, beside the rule file you are about to write:

```kotlin
fun a() {
    // ruleid: proj.kt.no-sleep
    Thread.sleep(10)
    // ok: proj.kt.no-sleep
    delay(10)
}
```

The line after `// ruleid: <id>` must be flagged; the line after `// ok: <id>` must not. Any other
flagged line is also a failure.

## 2. Write the rule

`qa/rules/no-sleep.yml` is a Semgrep rule file ([syntax](https://semgrep.dev/docs/writing-rules/overview)):

```yaml
rules:
  - id: proj.kt.no-sleep
    languages: [kotlin]
    severity: ERROR
    message: >-
      Do not sleep a worker. Run: kotlin-qa rule-doc proj.kt.no-sleep
    pattern: Thread.sleep($X)
    metadata:
      hazard: A sleeping worker holds its thread and its wake lock for nothing.
```

The id is dotted lower case. The message ends with the `Run:` pointer; `metadata.hazard` names the
harm. Without them `kqaci.rules.unnamed` fails.

## 3. See it red

```bash
kotlin-qa rule proj.kt.no-sleep qa/rules/no-sleep.kt     # exit 1: it fires on the red line
kotlin-qa rule proj.kt.no-sleep app/                     # the real instances, before any fix
```

Commit the rule and fixture while the instances are still present. That commit is the red.

## 4. Document it

`qa/defences/proj.kt.no-sleep.md`, with exactly these headings:

```markdown
# proj.kt.no-sleep

## What it flags
## Why
## How to fix correctly
```

`kotlin-qa docs-check` fails until the page is complete.

## 5. Fix the instances, then regenerate the summary

```bash
kotlin-qa run
kotlin-qa summary
```

If a class of defect has no syntactic pattern, do not write a rule that guesses. Write the
no-pattern sentence in the project's record of defences instead, saying why no pattern fits.
