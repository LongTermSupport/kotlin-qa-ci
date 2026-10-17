# kqaci.suppression.unscanned

## What it flags

A source file the suppression scan could not read.

## Why

A file that cannot be read cannot be checked for suppressions, so it could hide any number of them.

## How to fix correctly

Make the file readable as UTF-8, or exclude generated files that are not source with scan_exclude (which itself needs a record exception).
