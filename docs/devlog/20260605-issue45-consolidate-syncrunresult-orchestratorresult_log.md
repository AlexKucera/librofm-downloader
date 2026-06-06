# Slice 9: Consolidate SyncRunResult / OrchestratorResult

> **Date:** 2026-06-05
> **Type:** issue
> **Reference:** [Issue #45](https://github.com/AlexKucera/librofm-downloader/issues/45) — Parent: #36 PRD-003

## Goal

Eliminate structural duplication between `SyncRunResult` (7 fields) and `OrchestratorResult` (6 fields). They shared 6 of 7 fields with `SyncRunResult` adding only `fatal_error`. Two nearly-identical frozen dataclasses were at risk of drift if a field was added to one but not the other.

## What Was Done

- Refactored `SyncRunResult` to use **composition** — wraps an `OrchestratorResult` field instead of duplicating its 6 fields
- Added 6 delegating `@property` methods to `SyncRunResult` that delegate to the wrapped `OrchestratorResult` (downloaded_count, skipped_count, failed_count, failed_books, skipped_books, interrupted)
- Eliminated bridge copy code in `sync_run()` — field-by-field unpacking (20+ lines) collapsed to `SyncRunResult(orchestrator_result=result)`
- Updated 4 mock constructions in `test_cli.py` to use composition form
- Added 2 TDD tests in `TestSyncRunResultComposition` proving delegation and defaults
- All 172 tests pass (including 12 CLI tests + 2 new composition tests)

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| **Composition over inheritance** | Frozen dataclass inheritance is awkward (field ordering, default constraints). Composition is explicit and lets `OrchestratorResult` remain the single source of truth |
| **Delegating properties** | Preserves public interface — `cli.py` and all test code that reads `.interrupted`, `.downloaded_count` etc. works unchanged. No caller changes needed for field reads |
| **Default `OrchestratorResult()` factory** | Early-return error paths (`fatal_error="Config error: ..."`) just pass `fatal_error=` and get zero counts automatically via default factory |
| **Kept `fatal_error` as direct field** | It's pipeline-level metadata (config/auth/fetch failures) that doesn't belong on `OrchestratorResult` (which represents download orchestration results) |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| `test_cli.py` broke with `TypeError: unexpected keyword argument` | Old-style construction `SyncRunResult(downloaded_count=2)` no longer valid — those are now properties, not dataclass fields | Updated 4 mock constructions to `SyncRunResult(orchestrator_result=OrchestratorResult(...))` |
| Subagent worker session crashed with stale extension context | GitNexus extension threw stale-ctx error in child session | Continued work directly in parent session — no code impact |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/sync_run.py` | `SyncRunResult` refactored: 2 fields (`orchestrator_result` + `fatal_error`) + 6 delegating properties; bridge code eliminated (−12 net lines) |
| `tests/test_cli.py` | Updated 4 mock `SyncRunResult` constructions to use composition form |
| `tests/test_sync_run.py` | Added `TestSyncRunResultComposition` (2 tests) |

## Acceptance Criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Single source of truth for download-count fields | ✅ PASS — `OrchestratorResult` is the sole definition |
| 2 | No copy-paste drift risk | ✅ PASS — `SyncRunResult` has no duplicated fields |
| 3 | All call sites updated | ✅ PASS — `cli.py`, `sync_run.py`, `test_cli.py` all updated |
| 4 | Full test suite passes | ✅ PASS — 172 passed, 0 failed |

## Open Items & Next Steps

None — issue is complete. All 4 acceptance criteria met.

---

*Log written by write-log skill*
