# kqaci.suppression.unrecorded

## What it flags

A suppression, in a comment, an annotation or a setting, that has no matching record exception.

## Why

Every route that silences a detector is a hole in the net. Holes are allowed only as recorded decisions.

## How to fix correctly

Prefer to fix the code. If the suppression is right, add a record exception for that identifier and that file with a justification of your own words, or remove the suppression.
