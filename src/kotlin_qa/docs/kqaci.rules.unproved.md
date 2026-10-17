# kqaci.rules.unproved

## What it flags

A custom rule whose fixture does not behave as marked: a marked red line it misses, or an unmarked line it flags.

## Why

The fixture is the rule's proof. If it disagrees with the rule, one of them is wrong.

## How to fix correctly

Run `kotlin-qa rule <id>` to see the mismatch and fix the rule or the fixture.
