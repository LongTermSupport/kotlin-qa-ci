# kqaci.shell

## What it flags

A ShellCheck finding in a tracked `.sh` or `.bash` script, from the ShellCheck release this library pins.

## Why

Shell fails quietly: an unquoted variable splits on a space, a failed command in a pipeline is ignored, a typo in a variable name expands to nothing. These are the defects that delete the wrong directory.

## How to fix correctly

Fix the script as ShellCheck's message says. Do not add `# shellcheck disable=`; it is a suppression and needs a record exception naming the code and the file.
