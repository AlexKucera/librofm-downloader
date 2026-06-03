# Multi-Bar Progress: Per-Book Identity Mapping (Issue #14)

> **Date:** 2026-06-03
> **Type:** issue
> **Reference:** https://github.com/AlexKucera/librofm-downloader/issues/14

## Goal

Upgrade both `ProgressReporter` (TTY/Rich) and `PlainTextReporter` (cron) from single-book singleton state (`_current_task`, `_current_book`) to a per-book identity mapping (`_tasks: dict[int, object]`, `_book_ids: dict[int, int]`). This enables N simultaneous progress bars or interleaved log lines when multiple books download concurrently.

## What Was Done

### ProgressReporter changes (`librofm_downloader/progress.py`):

- Replaced `_current_task` / `_current_book` / `_start_time` with bidirectional mapping:
  - `_tasks: dict[int, object]` — task_id → book
  - `_book_ids: dict[int, int]` — id(book) → task_id (uses `id()` because Book has unhashable list attributes)
- `start_download(book)` now returns `task_id` (int) — was `None`
- `update(completed, *, total, task_id=None)` — new optional `task_id` kwarg; looks up correct bar; falls back to most recently started for backward compat
- `complete(book)` — looks up task by `id(book)`, marks complete, removes from **both** mappings
- `fail(book, reason)` — looks up task by `id(book)`, stops task, removes from **both** mappings
- All methods are safe on unknown books (no-op if book never started)

### PlainTextReporter:

- No code changes needed — already stateless per-call design handles concurrent books naturally

### Test changes (`tests/test_progress.py`):

- Fixed 2 existing tests that referenced removed `_current_task` attribute to use returned `task_id` from `start_download()`
- Added 10 new tests in 2 test classes:
  - `TestMultiBarProgress` (9 tests):
    - `test_start_download_returns_task_id` — verifies return type is int
    - `test_two_simultaneous_bars` — 2 start_download calls create 2 independent tasks
    - `test_update_targets_correct_bar_by_task_id` — update(task_id=X) touches only X's bar
    - `test_complete_removes_only_its_bar` — complete(A) leaves B active
    - `test_fail_removes_only_its_bar` — fail(B) leaves A active
    - `test_summary_stops_progress_after_all_tasks_done` — summary() cleans up mappings
    - `test_update_without_task_id_falls_back_to_most_recent` — backward compat fallback
    - `test_complete_unknown_book_is_safe` — no-op on unknown book
    - `test_fail_unknown_book_is_safe` — no-op on unknown book
  - `TestMultiBookPlainText` (1 test):
    - `test_interleaved_start_complete_fail_lines` — 3 concurrent books produce correct interleaved output

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Use `id(book)` as dict key instead of `book` object | `Book` has list attributes (`authors`, `narrators`) making it unhashable. `id()` gives a unique integer key for the object's lifetime. |
| Bidirectional mapping (`_tasks` + `_book_ids`) | Both lookups are O(1): book→task_id (for complete/fail) and task_id→book (for internal tracking). Single dict would require linear scan for one direction. |
| `task_id=None` default with "most recent" fallback | Backward compatible — existing callers (cli.py) that don't pass task_id still work correctly for single-download scenarios. |
| No changes to PlainTextReporter | Already stateless per-call — each start/complete/fail is independent. Adding tracking would be YAGNI. |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| `TypeError: unhashable type: 'list'` | Used `book` object as dict key; Book has list attributes | Switched to `id(book)` as integer key |
| 2 existing tests failed with `AttributeError: _current_task` | Tests referenced old singleton attribute | Updated to capture `task_id` from `start_download()` return value |
| Test inserted into wrong class | `insert_after` anchor was at end of `TestMultiBookPlainText` not `TestMultiBarProgress` | Removed and re-inserted at correct class location |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/progress.py` | Replaced singleton state with per-book identity mapping; `start_download()` returns `task_id`; `update()` accepts optional `task_id`; `complete()`/`fail()` clean up mappings |
| `tests/test_progress.py` | Fixed 2 existing tests for new interface; added 10 new tests across `TestMultiBarProgress` (9) and `TestMultiBookPlainText` (1) |

## Open Items & Next Steps

- None — issue is complete. All 7 acceptance criteria met:
  - ✅ `start_download(A)` then `start_download(B)` creates two simultaneous progress bars
  - ✅ `update(task_id=X)` updates the correct bar
  - ✅ `complete("Book A")` removes only Book A's bar
  - ✅ `fail("Book B")` removes only Book B's bar
  - ✅ `summary()` stops progress cleanly after all tasks done
  - ✅ `PlainTextReporter` produces correctly interleaved output for concurrent books
  - ✅ **10 new tests** (6–8 requested), all **194/194 tests pass**, zero regressions

---
*Log written via TDD workflow*
