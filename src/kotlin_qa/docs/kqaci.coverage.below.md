# kqaci.coverage.below

## What it flags

Line coverage of the unit tests is below the project's `[coverage] minimum_line`, or no coverage report was written.

## Why

Code no test runs is code nobody has seen work. The minimum is a floor that only moves up: a change that lowers coverage fails the run instead of quietly eroding it.

## How to fix correctly

Add tests for the code the change touched. If the report is missing, check that the coverage task named in `[gradle] coverage_task` writes the file named in `coverage_report`. Do not lower the minimum to pass; raise it when coverage rises.
