# kqaci.format

## What it flags

Source that ktlint would reformat.

## Why

Formatting drift makes diffs noisy and reviews slower, and a formatter that is not enforced is ignored.

## How to fix correctly

Run `ktlint --format` and commit the result. Do not add a `ktlint-disable` comment; every suppression needs an exception in the project record.
