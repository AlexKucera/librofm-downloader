# Wire rename_chapters() into Download Pipeline

> **Date:** 2026-06-05
> **Type:** issue
> **Reference:** [Issue #34](https://github.com/AlexKucera/librofm-downloader/issues/34)

## Goal

Wire the `rename_chapters()` function (built in Issue #32) into the download pipeline so it runs automatically after MP3 extraction when `config.rename_chapters` is enabled (Issue #33). End-to-end: MP3 downloads → chapters renamed to `{num} - {book} - {chapter}.mp3` with visible user feedback.

## What Was Done

- **`_download_mp3()` return type changed** from `Path | None` to `tuple[Path | None, list[dict]]` — now returns `(output_dir, tracks)` on success, `(None, [])` on failure. The `manifest["tracks"]` data was already fetched but previously discarded.
- **`download_book()` gained `rename_chapters: bool = False` kwarg** — optional, keyword-only, defaults to `False` for backward compatibility.
- **New `_rename_and_log()` helper** in `downloader.py` — calls `rename_chapters()`, checks count mismatch before renaming, logs via `logger.info/warning`, and calls `reporter.chapter_renamed()` with an example filename for user-visible output.
- **Both MP3 success paths wired** — `m4b_mp3_fallback` fallback path (line ~282) and `mp3_only` path (line ~293) both unpack the tuple and call `_rename_and_log(result_path, mp3_tracks, book.title, reporter)`.
- **`sync_run.py` closure updated** — `_make_download_fn()` now captures `resolved_rename_chapters` as `_rc` and passes it to `download_book(..., rename_chapters=_rc)`. This completes the wiring chain: CLI flag → `sync_run()` resolution → closure → `download_book()` → `_rename_and_log()` → `rename_chapters()`.
- **User-visible rename feedback added** — new `chapter_renamed(count, book_title, example_name)` method on both `PlainTextReporter` and `ProgressReporter` in `progress.py`. Shows output like: `Renamed 14 chapter(s) for 'The River Has Roots' → '01 - The River Has Roots - Chapter 1.mp3'`
- **6 TDD integration tests** added in `TestRenameChaptersWiring` class covering all acceptance criteria.

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Return tracks tuple from `_download_mp3()` rather than re-fetching manifest | Avoids a second API call; manifest is already in memory. Tuple is simple, no new dataclass needed for internal use |
| Call rename in `download_book()` not inside `_download_mp3()` | Separation of concerns: `_download_mp3` downloads, `download_book` orchestrates (including post-processing like renaming). Keeps `_download_mp3` testable in isolation |
| Add `reporter` param to `_rename_and_log()` instead of importing console/rich | Keeps downloader module decoupled from output mechanism; reporter is injected by caller, testable with mock reporters |
| Check count mismatch BEFORE calling `rename_chapters()` | After `zip()` truncation, a 3-file/2-track scenario renames 2 files and returns 2 — looks like success. Pre-check catches the mismatch regardless |
| Default `rename_chapters=False` on `download_book()` | Backward compatible; existing callers don't need changes. Only the sync_run closure passes the resolved value |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| Test expected `01 - ...` zero-padding but got `1 - ...` | Zero-padding width = `len(str(track_count))`. With 2 tracks, width=1 (single digit). Test assumed 2-digit padding | Fixed test expectations to match actual zero-padding logic |
| Count mismatch warning never fired for 3 MP3s + 2 tracks | Original code only warned when `rename_chapters()` returned 0 AND tracks existed. But `zip(3_files, 2_tracks)` renames 2 files → returns 2 → info log fires, no warning | Moved mismatch check BEFORE calling `rename_chapters()`, comparing `len(mp3_files) != len(tracks)` directly |
| User couldn't tell if renaming ran — files looked same as unzipped | `_rename_and_log()` only called `logger.info()` which goes to logging ether, not terminal. No user-facing output at all | Added `chapter_renamed()` method to both reporter classes; `_rename_and_log()` calls it with first renamed filename as example |
| Libro.fm manifest returned null/empty `chapter_title` values | API data quality issue — some books have no chapter title metadata | `rename_chapters()` falls back to `"Chapter {num}"` pattern (built in Issue #32). Not a bug, just data-dependent behavior |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/downloader.py` | `_download_mp3()` returns tuple; `download_book()` accepts `rename_chapters` kwarg; new `_rename_and_log()` helper with reporter feedback; both MP3 paths wired |
| `librofm_downloader/sync_run.py` | Closure captures `resolved_rename_chapters`, passes to `download_book(rename_chapters=_rc)` |
| `librofm_downloader/progress.py` | `chapter_renamed(count, title, example)` on PlainTextReporter + ProgressReporter |
| `tests/test_downloader.py` | 6 new tests in `TestRenameChaptersWiring` class (mp3_only rename, m4b-only skip, fallback rename, false-skip, count-mismatch warning, verbose logging) |

## Open Items & Next Steps

- [ ] Consider adding per-file rename logging in verbose mode (`-v`) — currently only shows summary line with one example filename
- [ ] Libro.fm chapter title quality varies widely; some books get generic "Chapter N" names. Future enhancement could scrape chapter titles from alternate sources (Audible API, etc.)
- [ ] ID3 tag writing not in scope (issue mentions this explicitly as out of scope)

---

*Log written by write-log skill*
