# kqaci.suppression.blanket

## What it flags

A suppression that silences a tool without naming the identifier, such as `@SuppressLint("all")` or a bare `ktlint-disable`.

## Why

A blanket suppression also silences every finding added to that code later.

## How to fix correctly

Name the identifier you mean to silence, then record that exception.
