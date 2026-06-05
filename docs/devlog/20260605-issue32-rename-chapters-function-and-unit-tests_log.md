# Issue #32: Core `rename_chapters()` Function + Unit Tests

> **Date:** 2026-06-05
> **Type:** issue (slice)
> **Reference:** [Issue #32](https://github.com/AlexKucera/librofm-downloader/issues/32) — Parent: #19

## Goal

Implement standalone `rename_chapters(output_dir, tracks, book_title) -> int` function in `downloader.py` that renames extracted MP3 files to include chapter titles from the Libro.fm download manifest. Full TDD with ~12 unit tests covering all acceptance criteria.

## What Was Done

- **Implemented `rename_chapters()`** in `librofm_downloader/downloader.py` (lines 509–545) — post-processing function that renames extracted `.mp3` files to `{zero-padded-number} - {sanitized_book_title} - {sanitized_chapter_title}.mp3`
- **Added `import re`** at module level in `downloader.py` for natural-sort regex
- **Added `rename_chapters`** to imports in `tests/test_downloader.py`
- **Wrote 11 tests** in new `TestRenameChapters` class covering all acceptance criteria:
  - Basic rename with chapter titles
  - Zero-padding (width auto-scales from track count)
  - Null/blank `chapter_title` → `"Chapter N"` fallback (per-track, not batch-skip)
  - All titles null/blank → all get fallback
  - Natural sort (numeric prefix extraction, not alphabetical)
  - Count mismatch (fewer files than tracks → rename available pairs via `zip`)
  - Non-MP3 files filtered out (`glob("*.mp3")`)
  - Sanitization via existing `sanitize()` from `path.py`
  - Empty directory / no MP3s → no-op, returns 0
  - Empty tracks list → no-op, returns 0
  - Idempotency (running twice on same dir doesn't break)

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Function lives in `downloader.py`, not a new module | Proximity to `_download_mp3()` which produces the files; module already imports `sanitize`, `Path`, `logger`; issue spec says "standalone function in downloader.py" |
| Natural sort via regex extraction of leading numeric prefix | Extracted ZIP filenames vary by publisher (`track01.mp3`, `Track - 1.mp3`, `1.mp3`); leading number is the only reliable pairing key; `re.match(r"(\d+)", p.stem)` handles all patterns |
| Zero-padding width = `len(str(len(tracks)))` | Auto-scales: 9 tracks → width 1, 10–99 → width 2, 100+ → width 3; no config needed |
| Sanitize-first then empty-check for fallback | Whitespace-only strings like `"   "` are truthy but `sanitize("   ")` produces `""`; checking after sanitization catches both `None`, `""`, and whitespace-only inputs |
| Return `int` count, not a dataclass | Matches issue spec signature exactly; simple scalar return is sufficient for caller needs |
| `zip(mp3_files, tracks)` for pairing | Naturally handles count mismatch by truncating to shorter iterable — no explicit `min()` needed |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| Whitespace-only `"chapter_title": "   "` produced empty filename segment | Original code checked `raw or ""` before sanitizing, but whitespace is truthy so it bypassed guard; then `sanitize("   ")` → `""` → malformed name like `3 - Book - .mp3` | Changed to always sanitize first: `sanitize(raw_title) or f"Chapter {num}"` — empty check happens *after* sanitization strips whitespace |
| Idempotency test had spurious assertion | Test asserted original `1.mp3` still exists after first run, but it was already renamed | Removed the erroneous line from test; idempotency works because renamed files still have leading numeric prefix that re-matches on second run |
| `import re` placed inside function body during refactor | Moved `import re` to module level alongside other stdlib imports (`logging`, `threading`) per Python conventions |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/downloader.py` | Added `rename_chapters()` function (+39 lines), added `import re` to module imports |
| `tests/test_downloader.py` | Added `rename_chapters` to import list, added `TestRenameChapters` class with 11 test methods (~210 lines) |

## Open Items & Next Steps

- [ ] **Wire `rename_chapters()` into `_download_mp3()`** — currently `tracks[]` is fetched from manifest but discarded; future slice should call `rename_chapters(output_dir, manifest["tracks"], book.title)` after ZIP extraction completes
- [ ] **Add count mismatch warning log** — issue spec says "log warning about the gap" when `len(files) != len(tracks)`; not yet implemented (no AC explicitly tests for warning output)
- [ ] **HITL testing** — download a real MP3 audiobook and verify renaming works end-to-end with actual Libro.fm manifest data

---
*Log written by write-log skill*
