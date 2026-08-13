# ADR-0004: Tauri and Vue Runtime Ownership

- Status: Accepted
- Date: 2026-08-12

## Context

Macro Studio is being migrated from a single Tkinter process to a Vue 3 frontend, a Tauri desktop shell, and a Python automation backend. The desktop app needs to discover the backend without a fixed port or a persisted credential, and it must clean up the backend when the window exits.

## Decision

- Keep the Vue application in `frontend/` and the Tauri shell in `src-tauri/`.
- Let Rust own the Python sidecar lifecycle.
- In development, start `python -m backend.main` from the repository root.
- In production, expect `sidecars/macro-studio-backend.exe` in the Tauri resource directory.
- Read the first JSON line from the sidecar as the readiness contract.
- Deliver the loopback host, random port, API version, and one-time token to Vue through a Tauri command and events.
- Never persist the session token in frontend storage or project configuration.
- Stop and wait for the child process when Tauri exits.
- Use `debug = 0` for the Rust development profile to reduce Windows debug link time and artifact size.

## Current Scope

The Vue run center connects to the versioned local API, renders playlists and runner state, and consumes live WebSocket events. The API runner is still simulation-only. Real Windows input remains in the Tkinter executor until its behavior is moved behind the backend boundary.

The production Python executable is not generated in this phase. A later packaging phase will build that sidecar, include its native dependencies, and validate an installer on a clean Windows environment.

## Consequences

- The development desktop app starts with one command and does not require manual port or token entry.
- Browser-only frontend development can still use explicit environment variables.
- A backend crash can be surfaced as a Tauri event and does not leave a stale connection in Vue.
- Production packaging remains intentionally blocked until the Python sidecar artifact exists.
