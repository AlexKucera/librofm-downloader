# Slice 5: Accompanying Files + Output Structure

> **Date:** 2026-06-03
> **Type:** slice
> **Reference:** [Issue #7](https://github.com/AlexKucera/librofm-downloader/issues/7)

## Goal

Implement PDF extras and cover art download, completing the output structure rules. Build client endpoint for PDF URLs, downloader logic for accompanying files with config toggles, non-critical failure handling, and verify directory layout behavior.

## What Was Done

### Client Module — `librofm_downloader/client.py`
- Added `fetch_pdf_extra_url(isbn, filename, transport)` method — `GET /api/v10/library/{isbn}/pdf_extra_url?filename={name}` → returns CDN URL string
- Raises `AuthError` if called before authentication
- Follows existing pattern from `fetch_m4b_url` and `fetch_download_manifest`

### Downloader Module — `librofm_downloader/downloader.py`
- Added `_cover_filename_from_url(url)` — derives cover filename from URL path, defaults to `"cover.jpg"`
- Added `_download_cover(url, output_dir, transport)` — streaming download with `.partial` → atomic rename pattern; returns `Path | None`; failures log warning, don't raise
- Added `_download_pdf(url, filename, output_dir, transport)` — same streaming pattern for PDF extras
- Added `download_accompanying_files(book, output_dir, config, client, transport)` — orchestrates cover + PDF downloads based on config toggles (`download_covers`, `download_extras`); returns list of successfully downloaded Paths; all failures are non-critical (warnings only)
- Wired `download_accompanying_files` into `download_book()` — called after successful audio download in all 3 format strategy paths (`m4b_mp3_fallback`, `mp3_only`, `m4b_only`)
- Added optional `config` parameter to `download_book()` for accompanying file settings

### CLI — `librofm_downloader/cli.py`
- Updated `download_book()` call to pass `config=config` parameter

### Tests — 12 new tests (122 → 134 total)
**`tests/test_client.py` — TestFetchPdfExtraUrl (2 tests):**
- `test_returns_pdf_url_when_available` — verifies CDN URL returned from API
- `test_raises_auth_error_if_not_authenticated` — verifies auth guard

**`tests/test_downloader.py` — TestDownloadAccompanyingFiles (7 tests):**
- `test_downloads_cover_art_to_correct_location` — cover downloaded to output dir
- `test_downloads_pdf_extra_to_correct_location` — PDF downloaded via mocked client
- `test_uses_partial_file_then_atomic_rename` — verifies .partial file cleaned up after download
- `test_download_extras_false_skips_pdf` — config toggle skips PDF
- `test_download_covers_false_skips_cover` — config toggle skips cover
- `test_cover_download_failure_logs_warning_no_exception` — 500 error → no exception
- `test_pdf_download_failure_logs_warning_no_exception` — API error → no exception

**`tests/test_downloader.py` — TestOutputStructure (4 tests):**
- `test_book_with_extras_creates_subdirectory` — `needs_subdirectory=True` with cover_url
- `test_book_without_extras_is_flat` — `needs_subdirectory=False` without extras
- `test_resolve_output_dir_creates_subdir_for_extras` — subdirectory path when extras present
- `test_resolve_output_dir_flat_for_no_extras` — flat path when no extras

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| `download_accompanying_files` takes optional `client` param | PDF URL fetch requires authenticated client; cover download doesn't. Making it optional keeps backward compatibility and makes the dependency explicit |
| Separate `_download_cover` and `_download_pdf` functions | Cover derives filename from URL; PDF takes explicit filename. Different enough to keep separate rather than over-abstract |
| Non-critical failure handling (warnings, no exceptions) | Per issue spec: "failure to download an accompanying file logs a warning but does not cause the book to be marked as failed" |
| Config toggles checked inside `download_accompanying_files` | Keeps the toggle logic co-located with the download logic; caller doesn't need to know about the internals |
| Added `config` param to `download_book` | Cleanest way to pass config through the orchestration layer without global state or coupling |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| `NameError: name 'download_accompanying_files' is not defined` | Function defined in `downloader.py` but not imported in test file | Added to import list in `test_downloader.py` |
| `NameError: name 'unittest' is not defined` | PDF test used `unittest.mock.patch` but `unittest` wasn't imported | Added `import unittest` to test file imports |
| Mock patch path error for `LibroFmClient.fetch_pdf_extra_url` | Tried to patch `librofm_downloader.downloader.LibroFmClient` but it's not imported there | Changed approach: pass mock client object directly via new `client` parameter |
| `test_resolve_output_dir_flat_for_no_extras` assertion wrong | Expected `output_dir == base` but `_resolve_output_dir` always includes author subdirectory | Fixed assertion to check for flat layout (no book-level subdir) rather than exact equality |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/client.py` | Added `fetch_pdf_extra_url()` method (+37 lines) |
| `librofm_downloader/downloader.py` | Added `_cover_filename_from_url`, `_download_cover`, `_download_pdf`, `download_accompanying_files`; wired into `download_book()` (+95 lines) |
| `librofm_downloader/cli.py` | Pass `config=config` to `download_book()` (+1 line) |
| `tests/test_client.py` | Added `TestFetchPdfExtraUrl` class (2 tests) |
| `tests/test_downloader.py` | Added `TestDownloadAccompanyingFiles` (7 tests), `TestOutputStructure` (4 tests); added imports |

## Open Items & Next Steps

- None — Issue #7 is complete with all 11/11 acceptance criteria met
- **134/134 tests passing** (12 new)

---
*Log written by write-log skill*
