# kqaci.rules.unnamed

## What it flags

A custom rule with no `metadata.hazard`, or whose message does not point at its documentation.

## Why

A rule whose reader cannot tell what harm it prevents is the first to be suppressed.

## How to fix correctly

Add `metadata.hazard` naming the harm, and end the message with `Run: kotlin-qa rule-doc <id>`.
