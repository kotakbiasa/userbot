# Backlog — DeltaUniverse/selfbot

This backlog lists deferred improvements and maintenance tasks. Items are non-urgent and should be worked on only when they block active development, are requested, or during scheduled maintenance.

## Priority rules
- New features take precedence.
- Work on backlog only if it blocks current work, repeats 3+ times, is requested, or during downtime.

## Summary
- Items: 40+
- Estimated effort: 30–40 hours
- Last updated: 2025-10-19
- Next review: 2025-11-19

## Code quality (low priority)
- Add type hints for core classes (Selfbot, Module, Listener). — 2–4h
- Add docstrings for public APIs. — 2–4h
- Extract repeated error handling into a decorator/context manager. — 2–3h
- Standardize handler naming (on_*, cmd_*, handle_*). — 1–2h

## Testing (medium)
- Unit tests for database operations and core utils. — 8–12h
- Listener lifecycle tests (register/unregister, dispatch). — 3–5h
- Integration tests for module loading and DB connections. — 6–8h

## Features (deferred)
- Command aliases, hot-reload modules, rate limiting, admin-only decorator, logging config. Estimates: 1–10h each depending on complexity.
- Suggested modules: stats, scheduler, auto-reply, media-group support, DB backup/restore.

## Security (review before public)
- Audit DB queries and parameterization. — 2–4h
- Review eval/exec in debug module; add safeguards. — 2–3h
- Sanitize telegraph HTML/markup inputs. — 1–2h
- Design simple permission model. — 3–5h

## Infrastructure
- Docker multi-arch, health checks, image size optimization. — 3–6h
- DB migrations (Alembic), backups, connection pooling. — 4–8h
- CI/CD pipeline with lint and tests. — 3–6h

## Known issues
- Long-running eval may time out.
- Large purge operations need batching.
- Telegraph module needs better HTML edge-case handling.

## Promotion checklist (backlog → active)
1. Create an issue with acceptance criteria and tests.
2. Assign milestone and owner.
3. Implement in a PR with tests for critical changes.

Last updated: 2025-10-19
Next review: 2025-11-19
