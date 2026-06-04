# Thread-Safe DownloadHistory.write() (Issue #13)

> **Date:** 2026-06-03
> **Type:** issue
> **Reference:** https://github.com/AlexKucera/librofm-downloader/issues/13

## Goal

Make `DownloadHistory.write()` safe for concurrent callers by adding a `threading.Lock`. Multiple worker threads call `history.write()` simultaneously when books finish downloading in parallel.

## What Was Done

- Added `import threading` and `self._lock = threading.Lock()` to `DownloadHistory.__init__()` (line 5, line 29 of `history.py`)
- Wrapped `write()` body with `with self._lock:` around both `_data` mutation and `_flush()` (lines 57-59)
- Left `is_downloaded()` and `find()` lock-free — CPython dict reads are atomic, and these are best-effort checks where stale reads are acceptable
- Added 5 new tests in `TestThreadSafety` class:
  - `test_has_lock_attribute` — verifies `_lock` exists and is a `threading.Lock`
  - `test_write_acquires_lock` — monkey-patches `_flush` to be slow; asserts lock is held during execution
  - `test_concurrent_writes_no_lost_entries` — 20 threads writing simultaneously; all entries must be findable
  - `test_concurrent_writes_produce_valid_json` — concurrent writes must produce parseable JSON with correct entry count
  - `test_sequential_behavior_unchanged` — regression guard: sequential write/read/find still works

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Lock only in `write()`, not `is_downloaded()`/`find()` | Issue spec says stale reads are acceptable; CPython GIL makes single-key dict reads atomic anyway. Avoids unnecessary contention on read-hot paths. |
| `threading.Lock` (mutex) not `RLock` | `write()` never calls itself recursively, so reentrancy is unnecessary. Mutex is lighter. |
| Test lock-holding via slow-flush monkey-patch | Directly observable proof that the lock is acquired *during* execution, not just before/after. More robust than checking unlocked state on both sides. |
| 20 threads for concurrency tests | Enough to create real contention on a GIL-released I/O-bound path (`_flush` does disk write), but fast enough that tests complete in <0.1s. |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| Test file corruption (duplicate lines) | Multiple `insert_after` edits on stale anchors caused content duplication | Used `replace_lines` with explicit start/end anchors to clean up the file |
| `TypeError: unexpected keyword argument 'author'` | `HistoryEntry` dataclass has no `author` field — only `isbn`, `title`, `format`, `path`, `downloaded_at` | Fixed test to use correct fields matching the actual dataclass definition |
| `TypeError: 'HistoryEntry' object is not subscriptable` | `find()` returns a `HistoryEntry` object, not a dict | Changed `found["title"]` to `found.title` attribute access |
| First version of `test_write_acquires_lock` was trivially passing | Only checked `locked() is False` before and after — true regardless of whether lock is used inside `write()` | Strengthened test to monkey-patch `_flush` with a slow version that checks `locked()` during execution |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/history.py` | Added `import threading`, `_lock` attribute in `__init__`, `with self._lock:` wrapper in `write()` |
| `tests/test_history.py` | Added `TestThreadSafety` class with 5 tests covering lock init, acquisition, concurrent integrity, JSON validity, regression |

## Open Items & Next Steps

- None — issue is complete. All 4 acceptance criteria met:
  - ✅ `_lock` attribute initialized in `__init__`
  - ✅ `write()` acquires lock before mutating + flushing
  - ✅ 5 new concurrency tests (3–4 requested)
  - ✅ **184/184 tests pass**, zero regressions

---
*Log written by write-log skill*
