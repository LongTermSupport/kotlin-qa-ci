# kqaci.kt.global-scope

## What it flags

A coroutine started with `GlobalScope.launch` or `GlobalScope.async`.

## Why

GlobalScope is never cancelled with the component that started the work. The coroutine keeps running, and keeps its references alive, after the service or screen is gone.

## How to fix correctly

Start the coroutine in a scope the owner controls and cancels: a `CoroutineScope` the service creates and cancels in `onDestroy`, `lifecycleScope`, or `viewModelScope`.
