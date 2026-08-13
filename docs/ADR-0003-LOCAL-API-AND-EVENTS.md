# ADR-0003: Add an authenticated loopback API and event stream

## Status

Accepted on 2026-08-11.

## Context

The Vue and Tauri migration needs a transport boundary that can run without importing Tkinter. The extracted runner, playlist, and preset services already contain the relevant rules, but they had no process-safe command interface or event stream. Directly exposing Windows automation at this stage would make an incomplete API capable of affecting the game before its lifecycle and cancellation behavior are verified.

## Decision

- CatalogService constructs songs, groups, presets, and current steps from the existing JSON documents and exposes snapshots and replacement operations.
- Catalog writes use callbacks so the API can reuse versioned atomic JSON storage while tests remain fully in memory.
- EventBus broadcasts immutable event envelopes through bounded per-client queues. A slow client loses its oldest event instead of blocking the runner.
- RunnerService owns the background worker and RunnerControl used by API commands.
- The first API runner uses a fast simulation executor. Requests with `simulation=false` return HTTP 501 until the real Windows executor is adapted behind the same interface.
- FastAPI exposes authenticated health, playlist, preset, runner, and WebSocket endpoints.
- Every HTTP request uses `X-Macro-Studio-Token`. WebSocket clients supply the same one-time token during connection.
- The sidecar binds only to `127.0.0.1`, chooses an OS-assigned port by default, disables API documentation and access logging, and prints one JSON readiness message for the Tauri parent process.
- Sidecar shutdown requests runner cancellation and waits briefly for the worker before exiting.

## Consequences

- A client can inspect and simulate a complete playlist run without creating a Tkinter root window.
- Python and the future TypeScript client share explicit Pydantic-compatible payload shapes.
- Tauri can discover the random port and token from sidecar standard output instead of relying on a fixed public port.
- WebSocket delivery is intentionally best effort. Clients recover authoritative runner state with `GET /api/runner` after reconnecting.
- Real input remains on the existing Tkinter path for now. The next backend step is to extract its action executor and inject it into RunnerService.
- The WebSocket token is present in the local connection URL. Access logging is disabled, and clients must not persist or display that URL.
