# kqaci.rules.invalid

## What it flags

A custom rule file that does not parse, lacks required keys, or reuses an id.

## Why

A rule that cannot be loaded silently protects nothing.

## How to fix correctly

Fix the file as the finding says. Ids are dotted lower case, such as `proj.kt.some-name`.
