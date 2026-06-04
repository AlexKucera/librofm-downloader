# Parallel Download Orchestrator — Issue #16

> **Date:** 2026-06-03
> **Type:** issue
> **Reference:** [Issue #16](https://github.com/AlexKucera/librofm-downloader/issues/16)

## Goal

Create a new `orchestrator.py` module that encapsulates the `ThreadPoolExecutor` lifecycle for parallel book downloads. Replaces the sequential `for` loop in `cli.py:run()` with a thread-pool-based concurrent execution model. All 4 blocking issues (#12 workers config, #13 history thread-safety, #14 multi-bar progress, #15 API rate limiter) were already complete.

## What Was Done

- **Created `librofm_downloader/orchestrator.py`** — New module with:
  - `OrchestratorResult` frozen dataclass: `downloaded_count`, `skipped_count`, `failed_count`, `failed_books` (list of `(Book, str)` tuples), `skipped_books` (list of `Book`)
  - `_raw_to_book(raw)` — Converts Libro.fm API dict → `Book` object (logic extracted from cli.py)
  - `_download_one(book, download_fn, reporter)` — Executes one book's download pipeline, returns `(book, result, error, was_skipped)`. Fires reporter `start_download` → `complete` or `fail`
  - `download_all_books(raw_books, *, workers, download_fn, reporter)` — Main entry point. Submits all books as futures to `ThreadPoolExecutor`, collects results via `as_completed()`, stable-sorts by original index
- **Refactored `librofm_downloader/cli.py`** — Replaced ~55-line sequential for-loop with orchestrator call:
  - Added `from librofm_downloader.orchestrator import download_all_books`
  - `_make_download_fn()` closure captures client/config/history/reporter/verbose
  - `result = download_all_books(new_books, workers=resolved_workers, ...)` replaces loop
  - Counts and lists consumed from `OrchestratorResult` directly
- **Created `tests/test_orchestrator.py`** — 20 new tests across 9 test classes:
  - `TestSequentialParity` (2): single + 3-book sequential with workers=1
  - `TestSkippedBooks` (2): skip detection, mixed download+skip
  - `TestFailedBooks` (2): exception capture as (book, reason), mixed success/skip/fail
  - `TestStableOrdering` (2): failed books sorted by original index despite concurrent completion order; skipped books same
  - `TestConcurrency` (1): wall time proves parallel execution (< sequential)
  - `TestFailureIsolation` (2): one fail doesn't block siblings; early fail doesn't prevent slow completions
  - `TestCallbackWiring` (2): called once per Book; Book has correct fields from raw dict
  - `TestReporterCallbacks` (4): success→start+complete; skip→start+complete; fail→start+fail; mixed counts
  - `TestEdgeCases` (3): empty list returns zero result; all-fail; all-skip
- **Fixed `tests/test_cli.py::TestIntegrationMixedResult`** — Updated mock from non-thread-safe `side_effect=[Path, Path, None, Exception]` list to deterministic ISBN-based function with `**kwargs` signature

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Function (`download_all_books`) + dataclass (`OrchestratorResult`) over class | User chose this. Simpler API, follows existing patterns (`download_book` is a function). Easy to mock in tests. No state needs to persist between calls. |
| Accept raw dicts, build Books internally | User chose this. Keeps cli.py thinner — just passes `new_books` through. Orchestrator owns the dict→Book conversion via `_raw_to_book()`. |
| Stable sort by original index on results | Issue spec requires "results grouped by status AND sorted back to original library order." Preserves user-visible ordering regardless of which thread finishes first. |
| `as_completed()` not `map()` | `as_completed()` yields results as each future finishes (better for progress reporting). `map()` would submit-order but block on slowest. We get both: completion-order processing + stable-sort output. |
| Skipped books fire `reporter.complete()` not `reporter.fail()` | Skip = successful handling of "no format available." The progress bar should close cleanly. Fail is reserved for exceptions only. |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| Test `test_download_fn_called_once_per_book` failed: ISBNs arrived out of order `[978111, 978333, 978222]` | With `workers=2`, threads complete in non-deterministic order. Original assertion used list equality expecting submission order. | Changed assertion to set membership: `assert call_isbns == {"978111", "978222", "978333"}` |
| CLI integration test `test_mixed_result_shows_correct_summary_and_exit_code` failed after refactor | Old mock used `side_effect=[Path, Path, None, Exception]` — a list that gets consumed sequentially. With concurrent workers, threads pop items non-deterministically from the shared list. | Replaced with deterministic `_download_side_effect(book, **kwargs)` that switches on `book.isbn`. Also added `**kwargs` to match `download_book`'s full signature. |
| Edit tool appended instead of replacing when fixing integration test | The `replace_lines` edit matched but content was appended after the anchor rather than replacing the target range. Required second pass to clean up duplicate code. | Manual fix: re-read file, identified the orphaned lines, replaced with corrected version. |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/orchestrator.py` | **New file** — ThreadPoolExecutor orchestration layer (~148 lines) |
| `librofm_downloader/cli.py` | Replaced sequential for-loop with `download_all_books()` call (-27 lines net) |
| `tests/test_orchestrator.py` | **New file** — 20 unit tests across 9 test classes (~638 lines) |
| `tests/test_cli.py` | Fixed integration test mock for thread-safety (ISBN-based side_effect) |

## Open Items & Next Steps

- None — issue complete, all acceptance criteria met

---

*Log written by write-log skill*
