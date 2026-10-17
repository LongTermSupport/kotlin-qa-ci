# kqaci.detekt

## What it flags

A Detekt finding in the project's Kotlin code, from the Detekt release this library pins and the configuration it ships, with the project's `qa/detekt.yml` on top.

## Why

Detekt reads the code with the compiler's type information and finds defects that formatting and Android Lint do not: swallowed exceptions, casts that can fail, coroutines that outlive their owner, complexity that hides bugs.

## How to fix correctly

Fix the code the finding points at. Do not add `@Suppress`, a baseline file or `ignoreFailures`: each is a suppression and needs a record exception. Loosening a rule belongs in `qa/detekt.yml` with the reason written directly above it (see `kotlin-qa rule-doc kqaci.detekt.unjustified`).
