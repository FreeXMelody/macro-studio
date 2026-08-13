# ADR-0001: Extract the sequence runner before adding the API

## Status

Accepted on 2026-08-11.

## Context

MacroStudio.run_sequence_worker() previously combined application orchestration with Tkinter concerns. It selected song presets, shuffled and looped jobs, handled pause and stop signals, retried image steps, found Windows targets, executed hardware actions, and wrote UI logs.

Vue and FastAPI cannot safely reuse that method because it depends on the MacroStudio window instance and Tkinter's after() callback.

## Decision

The first migration boundary is a UI-independent runner split into:

- backend.domain.runner.RunnerControl for status, pause, resume, stop, and interruptible waits.
- backend.application.sequence_runner.SequenceRunner for cycles, songs, steps, and image recovery.
- RunnerEvent for transport-neutral structured events.
- Tkinter callbacks that prepare a job, execute one existing step, and translate events into the current Chinese log messages.

The existing execute_step() remains in the Tkinter application during this stage. Its Windows input, image recognition, and transport calls are already working and will move behind infrastructure adapters separately.

## Consequences

- Tkinter and the future FastAPI service can share one orchestration engine.
- Pause, stop, completion, and failure now have explicit states.
- Image recovery behavior is covered without opening a desktop window.
- The UI still owns window lookup and hardware execution temporarily.
- Runner events can be serialized directly for a future WebSocket stream.

## Compatibility checks

- Disabled steps are skipped.
- The first failed image step retries itself twice.
- A later failed image step rolls back to the previous enabled image step.
- Exhausted recovery requests stop and finishes with failed.
- Empty jobs complete even when loop mode is requested.
- Existing Tkinter log text and action execution calls remain unchanged.

## Next boundary

Create application services for playlists, presets, targets, and settings. After those services own persistence and validation, add a local FastAPI transport that calls them and publishes RunnerEvent.to_dict() over WebSocket.
