# kqaci.kt.await-no-timeout

## What it flags

A call to `Tasks.await(task)` with no timeout argument.

## Why

A Play-services task that never completes blocks its thread for ever. In a background worker that means the worker is held until the operating system kills the process, and nothing reports it.

## How to fix correctly

Pass a timeout: `Tasks.await(task, 60, TimeUnit.SECONDS)`, and handle the `TimeoutException` as a failed attempt that is retried. Do not wrap the call in a catch that hides the timeout.
