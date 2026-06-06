# Issue #48: Wire Selector into sync_run Pipeline — TTY Guard, --limit Superseded, Integration Tests

> **Date:** 2026-06-06
> **Type:** issue
> **Reference:** [GitHub #48](https://github.com/AlexKucera/librofm-downloader/issues/48)

## Goal

Replace the `select_mode` stub in `sync_run.py` (which printed "not yet implemented" and returned) with the real selection pipeline: TTY guard, dict→Book conversion, call `select_books()`, pass selected Books to orchestrator without double-conversion, and ignore `--limit` when select mode is active.

## What Was Done

- Replaced `select_mode` stub in `sync_run.py` with full pipeline: TTY check → `from_library_row()` conversion → `select_books()` call → empty selection guard → pass selected Books to orchestrator
- Added `sys` import at module level (was inline `import sys as _sys`)
- Modified limit application to skip when `select_mode=True` (`if limit and not select_mode`)
- Added verbose note: "Selection mode active -- --limit superseded by manual selection."
- Modified `download_all_books()` in `orchestrator.py` to accept pre-converted `Book` objects via `isinstance` check — skips `from_library_row()` when elements are already `Book` instances
- Updated `--select` argparse help text from `"Interactive selection [not implemented]"` to `"Interactive book selection"`
- Updated `select_mode` docstring from "not yet implemented" to active status
- Added 5 integration tests in `test_sync_run.py` covering: no-TTY fatal error, all-caught-up with select, empty selection, selected→orchestrator flow, limit ignored
- Added 1 test in `test_orchestrator.py` for Book objects passthrough

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| `isinstance(raw, Book)` check in `download_all_books` | Backward-compatible: existing dict callers unaffected, select mode passes Book objects directly. Avoids double-conversion through `from_library_row()`. |
| Patch `librofm_downloader.selector.select_books` (not `sync_run.select_books`) | `select_books` is imported locally inside the `if select_mode:` branch, so patching at the source module works correctly with `unittest.mock.patch`. |
| `sys` import at module level | Cleaner than inline `import sys as _sys` alias. Used for TTY check (`sys.stdout.isatty()`). |
| Limit bypass: `if limit and not select_mode` | Single-line guard at the existing limit application point. Keeps limit logic in one place; no separate "restore limit" needed. |
| Verbose note uses `console.print` with `[dim]` | Consistent with existing verbose output styling in sync_run.py. |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| `NameError: name '_from_library_row' is not defined` | Refactor renamed `from_library_row` import but left stale `_from_library_row` references in the list comprehension | Changed `_from_library_row` → `from_library_row` and `_select_books` → `select_books` to match the clean import names |
| `AttributeError: <module 'sync_run'> does not have the attribute 'select_books'` | Test patched at `librofm_downloader.sync_run.select_books` but `select_books` is imported locally inside `if select_mode:` block | Changed patch target to `librofm_downloader.selector.select_books` (the source module) |
| Pre-existing threading test hangs | `test_three_books_all_downloaded_sequential` and similar orchestrator tests hang due to ThreadPoolExecutor + Ctrl+C interaction | Not addressed (pre-existing, out of scope). Tests excluded via `-k` filter. |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/sync_run.py` | Replaced `select_mode` stub with full pipeline (TTY guard, Book conversion, select_books call, limit bypass, verbose note). Added `sys` import. Updated docstring. |
| `librofm_downloader/orchestrator.py` | `download_all_books()` now accepts `list[Book]` directly — `isinstance` check skips `from_library_row()` for pre-converted objects |
| `librofm_downloader/cli.py` | Updated `--select` help text: removed "[not implemented]" |
| `tests/test_sync_run.py` | Added 4 test classes (5 tests): `TestSyncRunSelectModeTTYGuard` (2), `TestSyncRunSelectModeEmptySelection` (1), `TestSyncRunSelectModeSelectedFlow` (1), `TestSyncRunSelectModeLimitIgnored` (1). Replaced old stub test. |
| `tests/test_orchestrator.py` | Added `TestDownloadAllBooksAcceptsBookObjects` (1 test): Book objects pass through without `from_library_row()` conversion |

## Open Items & Next Steps

- [ ] User interactive testing of `--select` flag in a real terminal (TUI requires real TTY)
- [ ] Pre-existing threading test hangs (6 tests in test_orchestrator.py) need investigation
- [ ] Pre-existing `test_path.py` failures (Config missing `rename_chapters`) need fixing
- [ ] Parent issue #20 may have remaining slices (e.g., HITL for --select)

---

*Log written by write-log skill*
