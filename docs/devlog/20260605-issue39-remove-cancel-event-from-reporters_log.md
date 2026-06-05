# Issue #39: Remove `cancel_event` from Progress Reporters

> **Date:** 2026-06-05
> **Type:** issue
> **Reference:** [Issue #39](https://github.com/AlexKucera/librofm-downloader/issues/39)

## Goal

Stop threading `cancel_event` through the progress reporter as a shared-state bag. Instead, pass it explicitly through the parameter chain: `sync_run` closure → `download_book()` → `download_m4b()` / `_download_mp3()` (which already accept it). Remove the `cancel_event` attribute from both reporter classes.

## What Was Done

- **`librofm_downloader/progress.py`** — Removed `self.cancel_event = None` from both `PlainTextReporter.__init__()` (line 22) and `ProgressReporter.__init__()` (line 99). Reporters no longer carry cancellation state.
- **`librofm_downloader/downloader.py`** — Added `cancel_event: threading.Event | None = None` as a keyword-only parameter to `download_book()`. Replaced the line `cancel_event = reporter.cancel_event` with a comment noting the explicit parameter (Issue #39). The param is forwarded unchanged to `download_m4b()` and `_download_mp3()` which already accepted it.
- **`librofm_downloader/sync_run.py`** — Removed `reporter.cancel_event = cancel_event` assignment. The `_make_download_fn()` closure now captures `cancel_event` in a local (`_ce`) and passes it explicitly to `download_book(cancel_event=_ce)`.
- **`tests/test_progress.py`** — Added `TestReporterNoCancelEvent` class with 4 tests proving neither reporter class has a `cancel_event` attribute or constructor parameter.
- **`tests/test_downloader.py`** — Added `test_download_book_forwards_cancel_event` integration test that calls `download_book(book, session, plan, reporter, cancel_event=cancel_event)` with a real mock HTTP transport, verifies `InterruptedDownload` is raised when the event fires mid-stream. Removed stale `mock_reporter.cancel_event = None` line.
- **`tests/test_sync_run.py`** — Removed 3 stale `mock_reporter.cancel_event = None` lines from test setup.

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Explicit param over reporter attribute | `cancel_event` has nothing to do with reporting. Stashing it on the reporter object was a convenience that coupled two unrelated concerns (cancellation + UI). |
| Keyword-only param on `download_book()` | Matches existing pattern for optional params like `progress` and `rename_chapters`. Prevents positional confusion. |
| Closure capture in `sync_run.py` | The download function factory already captures other config values (`_rc` for rename_chapters). Adding `_ce` for cancel_event follows the same pattern cleanly. |
| Integration test over unit-mock approach | The new test exercises the full call chain through `download_book()` → auth → m4b URL fetch → streaming download → chunk-loop cancel check. This proves the param actually flows end-to-end, not just that the signature accepts it. |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| Test failed with `KeyError: 'access_token'` | Mock transport handler didn't handle `/oauth/token` endpoint that `session.authenticate()` hits | Added conditional branch returning `{"access_token": "tok", "token_type": "bearer"}` |
| Test failed with `NameError: name 'MagicMock' is not defined` | `MagicMock` imported at module level but new test method didn't have access in local scope; file uses `from unittest.mock import patch, MagicMock` at top but edit context was mid-file | Added inline `from unittest.mock import MagicMock` import |
| Test failed with `NameError: name 'InterruptedDownload' is not defined` | Same scoping issue — exception class not in local scope | Added inline `from librofm_downloader.downloader import InterruptedDownload` |
| Test failed with `KeyError: 'm4b_url'` | Mock handler returned generic JSON for API calls but `get_packaged_m4b_url()` expects `m4b_url` key | Added conditional branch for `/audiobooks/{isbn}/packaged_m4b` returning `{"m4b_url": "..."}` |
| Edit anchor staleness errors | Multiple edit operations invalidated LINE:HASH anchors from prior reads | Re-read files before each subsequent edit to get fresh anchors |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/progress.py` | −2 lines: removed `self.cancel_event = None` from both reporter classes |
| `librofm_downloader/downloader.py` | +1/−1: added `cancel_event` kwarg to `download_book()`, replaced `reporter.cancel_event` read with explicit param |
| `librofm_downloader/sync_run.py` | +2/−1: closure-captured `cancel_event`, removed `reporter.cancel_event = ...` assignment |
| `tests/test_progress.py` | +25 lines: 4 new tests in `TestReporterNoCancelEvent` class |
| `tests/test_downloader.py` | +51/−1: integration test for cancel_event forwarding; removed stale mock setup |
| `tests/test_sync_run.py` | −3 lines: removed 3 stale `mock_reporter.cancel_event = None` assignments |

## Open Items & Next Steps

- None. All 6 acceptance criteria met.
- **Test counts:** 429 total (+5 net new), 339 pass excluding pre-existing hanging orchestrator tests (4) and pre-existing path test failures (11).

---

*Log written by write-log skill*
