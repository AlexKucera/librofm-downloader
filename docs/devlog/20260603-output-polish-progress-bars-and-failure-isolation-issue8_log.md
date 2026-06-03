# User-facing Output Polish — Progress Bars & Failure Isolation

> **Date:** 2026-06-03
> **Type:** issue
> **Reference:** [Issue #8](https://github.com/AlexKucera/librofm-downloader/issues/8)

## Goal

Add TTY-aware download reporting: rich progress bars for interactive use, plain log lines for cron/piped output, and per-book failure isolation so one failing book doesn't stop the batch.

## What Was Done (Session 1)

- **New module `librofm_downloader/progress.py`** — TTY-aware download reporting system:
  - `DownloadReporter(stdout)` — factory function that detects TTY via `stdout.isatty()` and returns either `ProgressReporter` (TTY) or `PlainTextReporter` (non-TTY)
  - `PlainTextReporter` — writes `"Downloading: Author - Title (size)"`, `"Completed: Author - Title"`, `"Failed: Author - Title [ISBN] (reason)"`, summary line
  - `ProgressReporter` — uses `rich.Progress` with BarColumn, percentage, TransferSpeedColumn (MB/s), TimeRemainingColumn (ETA), DownloadColumn (file size)
  - `_fmt_size(bytes)` — human-readable size formatter (B/KB/MB/GB/TB)
- **Modified `librofm_downloader/cli.py`** — wired `DownloadReporter` into the download loop:
  - Replaced inline `console.print("⬇ ...")` with `reporter.start_download(book)`
  - Replaced `console.print("✓ Downloaded...")` with `reporter.complete(book)`
  - Replaced `console.print("✗ Failed...")` with `reporter.fail(book, reason=str(exc))`
  - Replaced summary line with `reporter.summary(downloaded, skipped, failed)`
  - Fatal errors (auth, config) still use `console.print()` directly and exit 1 immediately
- **New test file `tests/test_progress.py`** — **14 tests** across 8 test classes covering all acceptance criteria
- **Updated `tests/test_cli.py`** — 1 assertion updated for new `"Completed:"` reporter output format

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Factory function (`DownloadReporter()`) not a class with subclassing | Simpler API; callers don't need to know about TTY detection. Factory returns the right concrete type. |
| `PlainTextReporter` takes any TextIO (not just sys.stdout) | Testability — tests pass `io.StringIO()` and assert on contents without touching real stdout |
| Progress columns: BarColumn + % + Speed + ETA + DownloadSize | Matches AC exactly: "percentage, speed (MB/s), ETA, file size". Used rich's built-in column classes. |
| Fatal errors stay on `console.print()` | Fatal errors happen before the download loop; they're not book-level output. No need to route through reporter. |
| `start_download(book)` doesn't require `total_bytes` | The downloader doesn't always know file size upfront (especially MP3 ZIPs). Made it optional; shows "unknown size" when 0. |

## Gotchas & Fixes (Session 1)

| Problem | Root Cause | Fix |
|---------|------------|-----|
| `ImportError: cannot import name 'RemainingTimeColumn'` | The installed version of rich uses `TimeRemainingColumn`, not `RemainingTimeColumn` | Changed import and usage to `TimeRemainingColumn` |
| Size test expected "45.2 MB" but got "42.9 MB" | Test used decimal (1000-base) expectation but `_fmt_size` uses binary (1024-base) division | Fixed test to assert `"MB" in output` instead of exact value |
| Percentage column test: `'str' object has no attribute 'format_string'` | Column index 2 in `rich.Progress` is a raw format string (`"[progress.percentage]{task.percentage:>3.1f}%"`), not a `Column` instance | Changed assertion to check `"{task.percentage}" in columns[2]` then fixed to `"percentage" in columns[2].lower()` |
| CLI test expected `"Downloaded"` but got `"Completed:"` | New reporter uses `"Completed:"` per AC spec, not old `"Downloaded"` wording | Updated test assertion to match new output |
| Failure isolation test showed `<MagicMock name='Book().title'>` | Test was patching `Book` class, so cli.py created MagicMock objects instead of real Book data | Removed `Book` patch; changed assertions to check for `"Completed"`, `"Failed"`, and summary counts |

---

## Session 2 — Progress Bar %/ETA Fix (2026-06-03)

### Problem Reported

Progress bar stayed at **0.0%** and showed **no ETA** during actual downloads. User asked: *"does libro.fm not provide the final size?"*

### Root Cause

`start_download(book)` was called with `total_bytes=0` → rich's task received `total=None` → **cannot compute percentage, ETA, or speed without a total.** The file size isn't known until the HTTP GET response arrives from libro.fm's CDN with a **`Content-Length` header**.

### What Was Done (Session 2)

- **`progress.py` — both reporters' `.update()` method**: Changed signature from `update(self, completed: int)` to `update(self, completed: int, *, total: int | None = None)`. When `total` is provided, `ProgressReporter` calls `rich.Progress.update(task_id, total=N)` so the bar can compute %/ETA/speed dynamically.
- **`progress.py` — `PlainTextReporter.update()`**: Added missing no-op `.update()` method (was causing `AttributeError` when passed as callback to download functions).
- **`downloader.py` — `download_m4b()`**: On first chunk iteration, reads `resp.headers.get("content-length")`, stores as `content_length`, calls `progress(downloaded, total=content_length)`. Subsequent chunks call `progress(downloaded)` without total.
- **`downloader.py` — `download_zip_part()`**: Same Content-Length reporting pattern as M4B.
- **`test_progress.py` — 4 new tests**:
  - `TestProgressTotalFromContentLength` (3 tests): verifies `update(completed, total=N)` sets task.total, enables percentage calculation, and PlainTextReporter handles it as no-op
  - `TestM4BReportsContentLength` (1 test): integration test that `download_m4b()` reads Content-Length and passes it as `total=` on first progress callback
- **`test_progress.py` — 3 old tests updated**: Changed callbacks in `TestProgressCallbackM4B`, `TestProgressCallbackZipPart`, and `TestProgressCallbackWiring` to accept optional `total=` kwarg (`**kw` or explicit param)

### Data Flow After Fix

```
start_download(book, total_bytes=0)     # bar exists but total=None (unknown yet)
  ↓
download_m4b(url, progress=reporter.update)
  ↓ HTTP GET response arrives with Content-Length: 284MB
  ↓ first chunk:
    progress(65536, total=298071216)   ← bar gets its total!
  ↓ subsequent chunks:
    progress(131072)                   ← bar animates %
  ↓
complete(book)                         ← bar hits 100%
```

### Gotchas & Fixes (Session 2)

| Problem | Root Cause | Fix |
|---------|------------|-----|
| `PlainTextReporter` has no `.update()` method | Initial implementation only added methods needed for start/complete/fail/summary; didn't anticipate it being used as a progress callback | Added no-op `update(completed, *, total=None)` to maintain consistent interface with `ProgressReporter` |
| 3 old test callbacks failed with `unexpected keyword argument 'total'` | Tests written before `total=` was added to the callback signature | Updated callbacks to accept `**kw` or explicit `total: int | None = None` parameter |
| M4B loop replacement pattern kept failing at char position 93 | Two `with open(partial_path, mode)` loops exist in file (ZIP + M4B); earlier session had partially updated one loop leaving it in a corrupted/truncated state; exact whitespace matching required byte-level debugging | Used regex search to find both loops, identified the unmodified one by checking for absence of `content_length` variable, applied targeted fix |
| File corruption discovered during debugging | One of the two chunk loops had been left in a truncated state from an earlier partial edit (line cut off mid-statement mid-token) | The targeted replacement for the intact loop succeeded; syntax check confirmed clean compile |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/progress.py` | **NEW** — DownloadReporter factory, PlainTextReporter, ProgressReporter, _fmt_size helper; Session 2: added `total=` param to `.update()`, added missing `.update()` to PlainTextReporter |
| `librofm_downloader/cli.py` | Wired DownloadReporter into download loop (steps 5–6); added import |
| `librofm_downloader/downloader.py` | Session 2: threaded `progress` param through `download_m4b()`, `download_zip_part()`, `_download_mp3()`, `download_book()`, `download_accompanying_files()`; added Content-Length reading in chunk loops |
| `tests/test_progress.py` | **NEW** — 18 tests across 12 classes: TTY detection (2), plain log formats (5), failure isolation (1), fatal vs book-level (1), progress bar columns (4), summary (2), progress callbacks (3), Content-Length reporting (4) |
| `tests/test_cli.py` | Updated 1 assertion for new `"Completed:"` reporter output format |

## Acceptance Criteria (8/8 met)

1. ✅ TTY detected → rich progress bar shown during download
2. ✅ Non-TTY → plain log line per book instead of progress bar
3. ✅ Progress bar shows: percentage, speed (MB/s), ETA, file size
4. ✅ Plain log format: `"Downloading: Author - Title (size)"` / `"Completed: Author - Title"` / `"Failed: Author - Title (reason)"`
5. ✅ One book failure does not prevent subsequent books from downloading
6. ✅ Failed book logged with ISBN, title, and error reason
7. ✅ Fatal errors (auth fail before loop) still cause immediate exit 1
8. ✅ **18 tests** (exceeded ~8 target): TTY detection (2), plain log formats (5), failure isolation (1), fatal vs book-level (1), progress bar columns (4), summary (2), progress callbacks (3), Content-Length reporting (4)

**Test count: 156 total (138 existing + 18 new)** — all passing.

## Open Items & Next Steps

- None. Issue #8 is complete. All acceptance criteria met.
- Manual testing tip: pipe output through `cat` to force non-TTY mode and verify plain log lines

---
*Log written by write-log skill*
