# kqaci.kt.wakelock-no-timeout

## What it flags

A call to `acquire()` with no timeout on a wake lock.

## Why

A wake lock acquired without a timeout stays held if any path skips the release. The CPU then stays awake and the battery drains until the process dies.

## How to fix correctly

Acquire with a timeout that is longer than the work needs, `lock.acquire(10 * 60 * 1000L)`, and release in a `finally`. For work that outlives the timeout, renew the lock on a schedule rather than holding it unbounded.
