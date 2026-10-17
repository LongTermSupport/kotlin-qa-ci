# kqaci.semgrep.error

## What it flags

A Semgrep run that failed, produced no report, or could not read or parse a file completely.

## Why

A file Semgrep could not parse is a file no custom rule checked, and a run that reports nothing for it looks the same as a run that found nothing.

## How to fix correctly

Fix the syntax error or tool failure the finding quotes, then run again. Do not exclude the file from the scan to make the finding go; scan_exclude needs a record exception.
