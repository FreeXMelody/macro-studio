# ADR-0005: Explicit Real Automation Mode

- Status: Accepted
- Date: 2026-08-12

## Context

The first local API runner intentionally supported simulation only. Phase 4 needs the Vue run center to execute the same configured actions as the Tkinter application without copying Windows input primitives into HTTP routes or Vue components.

Real automation can move the pointer, change the clipboard, send keyboard input, and perform visual clicks. It must therefore remain an explicit user choice and must release held keys when stopped or when an action fails.

## Decision

- Add WindowsActionExecutor under backend/infrastructure.
- Continue using automation.py, vision.py, stage_transport.py, models, and the template renderer as low-level adapters.
- Load point groups, image targets, target-window settings, and input mode from the current configuration before each song.
- Keep simulation as the default API and UI mode.
- Require an explicit real selection and confirmation in the run center.
- Report the active mode in runner command and state responses.
- Poll F9 in the Python sidecar and route it through the same RunnerControl cancellation signal.
- Use interruptible waits for long key presses and always release temporary or persistent held keys in cleanup.
- Avoid logging pasted text, full request specifications, or session credentials.

## Consequences

- The new run center can execute existing click, image_click, paste, wait, keyboard, URI, HTTP, and log actions.
- Window-message mode remains available for background input without moving the physical pointer.
- Tests inject fake Windows bindings, so regression runs never send real mouse or keyboard input.
- The Tkinter executor remains in place during migration and continues to provide a fallback.
- Settings and target editing are not yet migrated to Vue; real mode currently consumes the existing compatible JSON configuration.
