# Issue #41: Extract `_stream_to_file()` Helper

> **Date:** 2026-06-05
> **Type:** issue
> **Reference:** [Issue #41](https://github.com/AlexKucera/librofm-downloader/issues/41)

## Goal

Extract a private `_stream_to_file(url, partial_path, final_path, ...)` helper from the ~30-line chunked-download loop duplicated across `download_m4b()`, `download_zip_part()`, and (per user request) also `_download_cover()` and `_download_pdf()`. Each caller becomes a thin wrapper that delegates streaming to the helper then does its own post-processing.

## What Was Done

- **Added `_stream_to_file()`** to `librofm_downloader/downloader.py` (L64–122) — private helper handling: `.partial` file creation, resume detection + Range header, httpx streaming chunk loop with cancel check + progress callback, atomic rename → final path. Signature: `(url, partial_path, final_path, transport=None, progress=None, cancel_event=None, headers=None) -> Path`.
- **Refactored 4 callers** to thin wrappers:
  - `download_m4b()` — derives partial path from output_path, calls helper, returns Path (~10 lines now)
  - `download_zip_part()` — derives paths from URL, calls helper, then extracts ZIP + cleanup (~15 lines now)
  - `_download_cover()` — protocol-relative URL fix, calls helper with custom headers, try/except→None (~15 lines now)
  - `_download_pdf()` — calls helper, try/except→None (~12 lines now)
- **5 new TDD tests** in `TestStreamToFile` class (`tests/test_downloader.py`):
  1. `test_fresh_download_streams_and_renames` — fresh download, atomic rename, return value
  2. `test_resume_from_partial_file` — appends to existing .partial, sends Range header, 206 response
  3. `test_cancel_mid_stream_raises_interrupted` — sets cancel_event via daemon thread mid-stream, asserts InterruptedDownload raised, .partial exists, final_path absent
  4. `test_progress_callback_receives_bytes_with_content_length` — first call gets `(downloaded, total=N)`, subsequent get `(downloaded)`, monotonically increasing
  5. `test_propagates_http_error` — HTTP 404 → `httpx.HTTPStatusError` raised, no final file created
- **All tests pass:** 224/224 (was ~220 baseline + 5 new - 1 net from prior session)
- **Net line reduction:** 557→535 lines (**−22 net**) in downloader.py

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Include `_download_cover` and `_download_pdf` in scope (beyond issue's original 2 functions) | User explicitly requested it; both had identical streaming loops with only minor differences (custom headers for cover, no resume/cancel/progress for either). Including them eliminates *all* duplication of this pattern in the codebase. |
| Helper takes explicit `partial_path` and `final_path` params (not derived internally) | Each caller has different path derivation logic (m4b uses suffix append, zip uses URL-derived name, cover/pdf use output path). Pushing path computation to callers keeps the helper focused on streaming only. |
| Optional `headers` dict param instead of hardcoding User-Agent inside helper | Only cover downloads need custom headers (`LibroFmSession.DEFAULT_HEADERS`). Other callers don't need them. Passing as optional keeps the helper generic. |
| Removed bare `except InterruptedDownload: raise` from helper | Python re-raises by default when you don't catch an exception. The original code had this no-op re-raise in both `download_m4b` and `download_zip_part`; the helper doesn't need it. |
| Condensed docstring from 20-line Args/Raises block to 5-line summary | The full parameter documentation is valuable but verbose for a private function. Kept the essential behavior description while reducing noise. |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| `IndentationError: unexpected indent` after removing `except InterruptedDownload: raise` | The old `try:` block wrapped the entire function body. Removing just the `except` left an orphaned `try:` with indented body but no handler → SyntaxError. Then removing `try:` left body still over-indented. | Removed `try:` keyword AND de-dented the body back to function-level indentation (22 lines re-indented). |
| Missing `return _stream_to_file(...)` line in refactored `download_m4b()` | First edit replaced the old body but the replacement text got mangled — the `return _stream_to_file(` line was missing between the partial_path assignment and the closing `)`. | Re-inserted the missing `return _stream_to_file(...)` call with correct parameters. |
| Parallel worker subagents writing to same test file | 4 subagents each wrote a different test method into `tests/test_downloader.py::TestStreamToFile`. GitNexus warned about concurrent edits but since each wrote at end-of-file they didn't conflict. | No fix needed — worked correctly. But noted that future parallel test-writing should confirm non-overlapping insertion points. |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/downloader.py` | Added `_stream_to_file()` (+70 lines). Refactored 4 functions to thin wrappers (−115 lines). Net −22 lines (557→535). |
| `tests/test_downloader.py` | Added `TestStreamToFile` class with 5 new tests (+~120 lines). Added `_stream_to_file` to imports. |

## Open Items & Next Steps

- None — all acceptance criteria met. Ready for commit.

---

*Log written by write-log skill*
