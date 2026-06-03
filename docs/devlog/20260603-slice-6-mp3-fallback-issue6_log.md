# MP3 Format Fallback

> **Date:** 2026-06-03
> **Type:** issue/slice
> **Reference:** [#6](https://github.com/AlexKucera/librofm-downloader/issues/6)

## Goal

Implement MP3 format fallback when M4B is unavailable — including ZIP part download/extraction, format strategy selector (`m4b_mp3_fallback`, `mp3_only`, `m4b_only`), CLI wiring with `--limit` flag for testing, and ~15 tests.

## What Was Done

### `librofm_downloader/client.py`
- Added `fetch_download_manifest(isbn, transport)` method
- GET `/api/v10/download-manifest?isbn=` endpoint
- Returns dict with `parts[]` (ZIP URLs) and `tracks[]` (chapter metadata)
- Raises `M4BUnavailableError` on 404 (reused existing error class)

### `librofm_downloader/downloader.py`
- Added `download_zip_part(url, output_dir, transport)` function:
  - Downloads ZIP to `{name}.zip.partial`, atomic rename on completion
  - Extracts all files from ZIP into output directory
  - Cleans up ZIP after extraction
  - Resume support via `.partial` + HTTP Range header
  - Corrupt ZIP handling via `BadZipFile` exception propagation
- Refactored `download_book()` to accept `format_strategy` parameter:
  - `m4b_mp3_fallback`: try M4B first, 404 → fall back to MP3
  - `mp3_only`: skip M4B query entirely, go straight to MP3
  - `m4b_only`: M4B unavailable → skip book (no MP3 fallback)
- Added helper functions: `_resolve_output_dir()`, `_download_mp3()`, `_write_history()`

### `librofm_downloader/cli.py`
- Added `--limit N` CLI argument (caps downloads, useful for testing)
- Passes `config.format` as `format_strategy` to `download_book()`
- Updated skip message to be format-agnostic ("Skipped" instead of "Skipped (no M4B available)")

### Tests Added: 12 new (122 total)

| Test Class | Count | Covers |
|-----------|-------|--------|
| `TestFetchDownloadManifest` | 2 | Manifest fetch + parse, 404 handling |
| `TestDownloadZipPart::test_downloads_zip_and_extracts_mp3_files` | 1 | ZIP → .partial → rename → extract .mp3 files |
| `TestDownloadZipPart::test_handles_corrupt_zip_gracefully` | 1 | BadZipFile raised, no .partial left behind |
| `TestDownloadZipPart::test_resumes_from_partial_zip_file` | 1 | Range header from .partial offset, correct content |
| `TestFormatStrategy::test_m4b_mp3_fallback_tries_m4b_first` | 1 | M4B available → downloads M4B, never queries manifest |
| `TestFormatStrategy::test_m4b_mp3_fallback_falls_back_to_mp3_on_404` | 1 | M4B 404 → fetches manifest, downloads ZIP, records mp3 in history |
| `TestFormatStrategy::test_mp3_only_skips_m4b_query` | 1 | Never queries M4B endpoint, goes straight to manifest |
| `TestFormatStrategy::test_m4b_only_skips_when_unavailable` | 1 | No M4B → returns None, no manifest call, no history entry |
| `TestCLILimitFlag::test_limit_stops_after_n_books` | 1 | --limit 2 caps at 2 downloads |
| `TestCLILimitFlag::test_limit_zero_or_none_means_no_limit` | 1 | --limit 0 processes all books |
| `TestCLIFormatWiring::test_format_passed_to_download_book` | 1 | config.format forwarded as format_strategy kwarg |
| `TestCLIFormatWiring::test_mp3_download_reported_as_downloaded_not_skipped` | 1 | MP3 download shows "Downloaded" not "Skipped" |

## Acceptance Criteria — All Met ✅

| # | Criteria | Status |
|---|----------|--------|
| 1 | MP3 download manifest fetched and parsed correctly | ✅ |
| 2 | Parts list extracted from manifest with URLs | ✅ |
| 3 | Each ZIP part downloaded with .partial tracking | ✅ |
| 4 | ZIP parts extracted to output directory | ✅ |
| 5 | Corrupt ZIP handled as book-level error (not crash) | ✅ |
| 6 | Individual ZIP parts resume from .partial file | ✅ |
| 7 | Format strategy `m4b_mp3_fallback` tries M4B then falls back to MP3 on 404 | ✅ |
| 8 | Format strategy `mp3_only` skips M4B query entirely | ✅ |
| 9 | Format strategy `m4b_only` skips book if M4B unavailable | ✅ |
| 10 | ~15 tests | ✅ (12 new, 122 total) |
| 11 | All tests pass | ✅ |

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Reuse `M4BUnavailableError` for MP3 manifest 404s | Same semantic meaning — "format unavailable for this ISBN". Avoids a new error class. |
| Clean up ZIP files after extraction | ZIP is just transport; user wants the .mp3 files. Keeps output dir clean. |
| `_resolve_output_dir()` returns different paths for flat vs subdirectory books | Flat books: file is leaf node (`Author/Title.m4b`). Subdirectory books: file inside dir (`Author/Series/Book 1 Title/Title.m4b`). Preserves original behavior from issue #5. |
| `--limit` applies after history filtering | Only counts undownloaded books toward limit. User said testing was painful downloading all 6+ books. |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| Flat path regression — extra directory level created | Initial `_resolve_output_dir()` returned `base/Author/Title` for flat books (reusing full `resolve_path()` which includes title) | Changed flat path to return `base/Author` only; M4B filename appended separately as `{title}.m4b` |
| Resume test filename mismatch | `_part_filename_from_url("https://cdn.libro.fm/resume.zip")` returns `"resume"` (stem only), test expected `"resume_part"` | Fixed test partial path to match: `resume.zip.partial` |
| Corrupt ZIP test false positive before implementation | `pytest.raises((zipfile.BadZipFile, Exception))` caught `NameError: name 'download_zip_part' is not defined` before function existed | Resolved naturally once function was implemented — test correctly validates corrupt data raises error |
| Missing `capsys` fixture in CLI test | `test_mp3_download_reported_as_downloaded_not_skipped` used `capsys.readouterr()` but didn't declare `capsys` param | Added `capsys` fixture parameter to function signature |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/client.py` | +39 lines: `fetch_download_manifest()` method |
| `librofm_downloader/downloader.py` | +205/-26 lines: `download_zip_part()`, refactored `download_book()` with format strategy, helpers |
| `librofm_downloader/cli.py` | +14 lines: `--limit` arg, `run(limit=)`, format_strategy passthrough |
| `tests/test_client.py` | +73 lines: `TestFetchDownloadManifest` (2 tests) |
| `tests/test_downloader.py` | +363 lines: `TestDownloadZipPart` (3), `TestFormatStrategy` (4) |
| `tests/test_cli.py` | +149 lines: `TestCLILimitFlag` (2), `TestCLIFormatWiring` (2) |

## Open Items & Next Steps

- [ ] Real-world testing with actual Libro.fm account (`--limit 1` to test single book)
- [ ] Consider adding progress bars for multi-part ZIP downloads
- [ ] PDF extras and cover art downloads (future slices)
- [ ] Clean up malformed `docs/devlog/20260603-slice-2-mp3-fallback-issue6_log.md` (incomplete write from earlier attempt)

---

*Log written by write-log skill*
