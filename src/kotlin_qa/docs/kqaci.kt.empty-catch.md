# kqaci.kt.empty-catch

## What it flags

A `try` whose `catch` block has no statements.

## Why

A failure that is caught and dropped leaves the app reporting success for work that did not happen, and leaves no trace for whoever investigates.

## How to fix correctly

Handle the failure: log it, change state so the user can see it, retry, or rethrow. If the failure truly cannot matter, catch the narrowest exception type and say why in a comment inside the block, which makes the block no longer empty.
