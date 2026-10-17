# kqaci.record.invalid

## What it flags

A record entry that cannot be used, or a record that cannot be read.

## Why

An exception with no person, date or specific reason cannot be reviewed, so it would silence a detector with nothing behind it.

## How to fix correctly

Fix the entry named in the finding: one file path, a person in decided_by, dates, and a justification of your own words naming the hazard accepted and the scope. Run `kotlin-qa record check`.
