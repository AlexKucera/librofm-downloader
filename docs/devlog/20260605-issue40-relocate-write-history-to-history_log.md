# Issue #40: Relocate `_write_history()` to `history.py`

> **Date:** 2026-06-05
> **Type:** issue
> **Reference:** [Issue #40](https://github.com/AlexKucera/librofm-downloader/issues/40) (PRD-003: Deepen Codebase Architecture)

## Goal

Move `_write_history()` from `downloader.py` to `history.py` as a module-level function, update all call sites, and remove persistence-related imports from `downloader.py` so it contains only download-related logic.

## What Was Done

- **Wrote TDD test first** (`test_write_history_creates_entry_via_history_module` in `test_history.py`) — imports `_write_history` from `librofm_downloader.history`, confirming it creates a correct `HistoryEntry` with proper ISBN/title/format/path/timestamp fields → **RED** (`ImportError`)
- **Moved `_write_history()`** to `librofm_downloader/history.py` as a module-level function (lines 72–92), added `Book` type-hint import with `# noqa: F401` annotation → **GREEN**
- **Updated `sync_run.py`** — changed import from `from librofm_downloader.downloader import _write_history, download_book` to separate imports: `download_book` from `downloader`, `_write_history` + `DownloadHistory` from `history`. Removed duplicate `DownloadHistory` import that was already present.
- **Updated `test_downloader.py`** — moved `_write_history` import from `downloader` block to standalone `from librofm_downloader.history import _write_history`
- **Cleaned up `downloader.py`** — removed `from librofm_downloader.history import HistoryEntry` import and the entire `_write_history()` function (was lines 521–537, 19 lines removed)

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| TDD approach for pure relocation | Even though no logic changes, writing test first proves the new location works and provides a regression guard |
| `# noqa: F401` on Book import | `Book` is only used in string type hints (`"Book"`); linter would flag as unused without suppression |
| Keep lazy `datetime` import inside function | Preserves existing pattern — datetime only needed at call time, not module load |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| Duplicate `_flush()` method after first edit | First `replace_lines` edit duplicated the method body instead of replacing it | Second edit removed the duplicate, kept original `_flush` + new `_write_history` |
| `TypeError: Book.__init__() missing required positional arguments` | Initial test used keyword-style args with wrong field order; `Book` requires `title`, `authors`, `narrators`, `isbn` as positional-or-keyword | Fixed test to pass all required fields correctly |
| Duplicate `DownloadHistory` import in sync_run.py | Added `DownloadHistory` to the new history import line, but old line still existed | Removed duplicate in follow-up edit |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/history.py` | **+20 lines** — added `_write_history()` module-level function + `Book` type-hint import |
| `librofm_downloader/downloader.py` | **−20 lines** — removed `HistoryEntry` import + `_write_history()` function |
| `librofm_downloader/sync_run.py` | Import fix — `_write_history` now from `history`; consolidated `DownloadHistory` import |
| `tests/test_history.py` | **+1 test, +26 net lines** — `TestWriteHistoryRelocated` class confirming relocation |
| `tests/test_downloader.py` | Import fix — `_write_history` now from `history` |

## Open Items & Next Steps

- None — this issue is complete. All 5 acceptance criteria met, full suite passes (~430 tests including pre-existing hangs).

---
*Log written by write-log skill*
