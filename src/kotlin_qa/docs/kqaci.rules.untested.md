# kqaci.rules.untested

## What it flags

A custom rule with no fixture, or a fixture lacking a `ruleid:` example or an `ok:` example for the rule.

## Why

A rule that has never been seen failing on bad code and passing on good code may do neither.

## How to fix correctly

Add a fixture beside the rule file with the same name and a `.kt` suffix. Mark the red line `// ruleid: <id>` and the green line `// ok: <id>`.
