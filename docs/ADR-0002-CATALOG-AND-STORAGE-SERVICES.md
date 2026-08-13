# ADR-0002: Centralize catalog rules and version local JSON documents

## Status

Accepted on 2026-08-11.

## Context

Song-group filtering, preset inheritance, reference updates, and JSON serialization were implemented directly in Tkinter callbacks. A future FastAPI client would otherwise need to duplicate those rules. The existing configuration files also had no schema marker and were written directly to their final paths.

## Decision

- PlaylistService owns group lookup, active-view filtering, runner job creation, song movement, and playlist serialization.
- PresetService owns step cloning, create/save/copy/rename/delete operations, reference updates, and song-over-group preset resolution.
- json_storage writes atomically through a temporary file and keeps the previous document as a .bak file.
- Saved dictionaries include _schema_version and _document_type metadata.
- The loader removes metadata before returning application data and continues to accept unversioned legacy documents.
- Metadata remains at the document root so the pre-migration main branch can ignore the extra fields and still read files created by the refactor branch.

## Consequences

- Tkinter and the future API use the same playlist and preset rules.
- Interrupted writes cannot leave a partially written primary JSON file.
- Users retain one previous local version for manual recovery.
- Backup files may contain the same private values as the primary local files and must remain ignored by Git.
- Model construction from raw JSON still lives in MacroStudio temporarily and is the next persistence boundary to extract.
