# Issue #43: Test Reorganization Cleanup Pass

> **Date:** 2026-06-05
> **Type:** issue
> **Reference:** [Issue #43](https://github.com/AlexKucera/librofm-downloader/issues/43)

## Goal

Reorganize three test-organization problems into a single cleanup pass so that each test file tests exactly one production module. All changes are move-only or delete — no logic changes to production code.

## What Was Done

### 1. Deleted 13 duplicate path test classes from `test_downloader.py` (L194–602, −409 lines)

Classes `TestSanitizeIllegalChars` through `TestNeedsSubdirectory` (13 classes, ~56 test methods) were **byte-for-byte identical** to existing classes in `test_path.py`. They tested `sanitize()`, `resolve_path()`, `needs_subdirectory()` — all imported from `path.py`, not `downloader.py`. Action: **delete** (not move), since `test_path.py` already had complete copies (plus one extra test in `TestNeedsSubdirectory`).

### 2. Moved 2 integration-style classes from `test_progress.py` → `test_sync_run.py`

- `TestFailureIsolationCLI` (L150–209) — mocked `sync_run.load_config`, `sync_run.LibroFmSession`, `sync_run.download_book`
- `TestFatalVsBookLevel` (L215–249) — same pattern, tests auth-fatal-exit behavior

These were sync_run pipeline integration tests living in the progress test file.

### 3. Deleted duplicated `TestParallelProgressCallbackWiring` (L1171–1254, −84 lines)

Copy 2 was character-for-character identical to Copy 1 (L1087–1170). Deleted the second copy.

### 4. Rescued orphaned test method (L1256–1289)

A valid 3-book interleaved plain text test (`test_interleaved_start_complete_fail_lines`) had no class header — it was syntactically inside the deleted duplicate class body due to 4-space indentation. Wrapped it in a new class `TestMultiBookPlainTextInterleaved`.

### 5. Fixed migrated tests to match actual APIs

The moved tests had been written against an older/stale API surface:

| Mismatch | Actual | Fix |
|----------|--------|-----|
| `result.downloaded` / `result.failed` | `result.downloaded_count` / `result.failed_count` (`SyncRunResult` fields) | Updated attribute names |
| `isinstance(result.fatal_error, AuthError)` | `fatal_error` is `str \| None`, stores error message string | Changed to `"auth" in result.fatal_error.lower()` |
| `captured.err` assertion | `console.print()` writes to stdout, not stderr | Changed to `captured.out` |
| `DownloadResult(isbn=..., ...)` | No `isbn` field; signature is `(status, path, format, error)` | Used `DownloadResult(status="downloaded", format="m4b", path=...)` |

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Delete path dups from downloader rather than move | Classes already existed identically in `test_path.py`; moving would create yet another copy to delete |
| Keep `sanitize`, `resolve_path`, `needs_subdirectory` imports in `test_downloader.py` | Downstream test classes (`TestOutputStructure`, `TestDownloadM4B`) still call these functions directly |
| New class wrapper for orphaned method | Method tests distinct scenario (3-book with `total_bytes`) vs existing `TestMultiBookPlainText` (2-book without); keeping separate preserves focused test intent |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| 5 `NameError: name 'needs_subdirectory' is not defined` after import cleanup | Over-aggressively removed `sanitize`, `resolve_path`, `needs_subdirectory` from imports assuming they were only used by deleted classes | Restored all 3 imports — grep confirmed downstream usage |
| `TypeError: Config.__init__() missing rename_chapters` (10 failures in `test_path.py::TestResolveOutputPlan`) | Pre-existing: Issue #33 added `rename_chapters` field but these tests weren't updated | **Not fixed** — out of scope for #43, pre-existing technical debt |
| `TypeError: DownloadResult.__init__() got unexpected keyword argument 'isbn'` | Moved test used stale API from before Issue #29 refactor | Fixed to use current `(status, path, format, error)` signature |
| `isinstance('string', AuthError)` assertion failure | `SyncRunResult.fatal_error` is `str \| None`, not exception instance | Changed to string containment check |
| Empty `captured.err` when checking auth failure message | `rich.console.Console.print()` writes to stdout, not stderr | Switched to `captured.out` |
| Orphaned method discovered during duplicate deletion | Missing `class` header — method was indented inside deleted duplicate class body | Wrapped in new `class TestMultiBookPlainTextInterleaved:` |

## Files Changed

| File | Change Summary |
|------|---------------|
| `tests/test_downloader.py` | Deleted L194–602 (13 duplicate path test classes, −409 lines). Cleaned path imports (kept 3 functions still used downstream). Net: **−406 lines** |
| `tests/test_progress.py` | Moved `TestFailureIsolationCLI` + `TestFatalVsBookLevel` to sync_run (−104 lines). Deleted duplicate `TestParallelProgressCallbackWiring` (−84 lines). Wrapped orphaned method in `TestMultiBookPlainTextInterleaved` (+35 lines). Net: **−153 lines** |
| `tests/test_sync_run.py` | Added 2 migrated classes + section header comment (+89 lines). Fixed 4 API mismatches in migrated tests. Net: **+89 lines** |

## Acceptance Criteria Report

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Tests for `path.py` functions live in `test_path.py`, not `test_downloader.py` | ✅ 13 duplicate classes deleted |
| 2 | Integration-style pipeline tests live in `test_sync_run.py`, not `test_progress.py` | ✅ 2 classes moved |
| 3 | No duplicated test classes remain in any test file | ✅ Duplicate `TestParallelProgressCallbackWiring` removed |
| 4 | Full suite passes with same total count (no tests lost/gained) | ⚠️ **374 tests** (was 430) — −56 = removed actual duplicates; orphan rescued (net 0 unique tests lost) |
| 5 | Each test file tests exactly one production module | ✅ See mapping below |

### Test File → Production Module Mapping (after cleanup)

| Test File | Module | Classes |
|-----------|--------|---------|
| `test_book.py` | `book.py` | 6 |
| `test_cli.py` | `cli.py` | 2 |
| `test_config.py` | `config.py` | 12 |
| `test_downloader.py` | `downloader.py` | 17 (was 30) |
| `test_history.py` | `history.py` | 7 |
| `test_orchestrator.py` | `orchestrator.py` | 11 |
| `test_path.py` | `path.py` | 16 |
| `test_progress.py` | `progress.py` | 22 (was 24) |
| `test_session.py` | `session.py` | 10 |
| `test_sync_run.py` | `sync_run.py` | 31 (was 29) |

**Verification:** `python -m pytest -q tests/test_downloader.py tests/test_progress.py tests/test_sync_run.py` → **168 passed, 0 failed**

## Open Items & Next Steps

- [ ] Fix pre-existing `test_path.py::TestResolveOutputPlan` failures (10 tests missing `rename_chapters` Config arg) — leftover from Issue #33
- [ ] Fix pre-existing `test_orchestrator.py` hang (3 Ctrl+C tests) — documented since Issue #17
- [ ] Consider whether `test_downloader.py` still needs direct `sanitize`/`resolve_path`/`needs_subdirectory` calls or if those test classes should also migrate to `test_path.py`

---

*Log written by write-log skill*
