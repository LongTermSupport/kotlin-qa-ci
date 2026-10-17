# kqaci.leaks

## What it flags

A credential-shaped string in a commit reachable from the checked-out history, found by gitleaks and shown redacted. A shallow clone checks only the commits it has, so CI should fetch the full history.

## Why

A secret in a repository is a secret in every clone and every fork, for ever: removing it from the next commit does not remove it from history.

## How to fix correctly

Remove the value, rotate the credential, and read it from the environment or a secret store. Do not add `gitleaks:allow` or a `.gitleaksignore` entry without a record exception naming the file; a real credential must be rotated, not allowed.
