# kqaci.detekt.unjustified

## What it flags

A rule entry in the project's Detekt overrides file that switches a rule off, raises a threshold, excludes a path or ignores an annotation, with no comment directly above it giving the reason.

## Why

A relaxed rule is a decision, and a decision with no recorded reason cannot be reviewed or ever revisited. The shipped configuration is strict on purpose; every departure from it must explain itself.

## How to fix correctly

Put a comment on the line directly above the rule saying why this project needs the change and what would make it unnecessary. A blank line between the comment and the rule breaks the link. Turning a rule on needs no reason.
