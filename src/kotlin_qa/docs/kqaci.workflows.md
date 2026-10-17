# kqaci.workflows

## What it flags

A finding from actionlint (a mistake in a GitHub Actions workflow) or zizmor (an insecure pattern in one: script injection through an untrusted expression, an unpinned action, a token with more permission than the job needs).

## Why

A workflow runs with the repository's credentials. A mistake wastes a run; an insecure pattern lets a pull request, an issue title or a compromised action act as the project.

## How to fix correctly

Fix the workflow: pin actions to a commit, give the job the least `permissions`, pass untrusted values through `env` instead of interpolating them into `run`. Do not add `zizmor: ignore` or an actionlint ignore entry without a record exception.
