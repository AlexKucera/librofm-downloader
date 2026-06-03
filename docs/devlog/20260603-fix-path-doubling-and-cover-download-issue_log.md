# Fix Path Doubling & Cover Download

> **Date:** 2026-06-03
> **Type:** issue
> **Reference:** Untracked bug (user-reported path doubling)

## Goal

Fix a path resolution bug where audiobook downloads produced doubled folder structures like:
```
audiobooks/Tiffany Crum/This Story Might Save Your Life/This Story Might Save Your Life.m4b
```
Instead of the correct flat or single-subfolder path. Also fix cover art downloads that were silently failing.

## What Was Done

### Bug 1: `needs_subdirectory()` treated `cover_url` as a subdirectory trigger
- **File:** `librofm_downloader/downloader.py`
- **Function:** `needs_subdirectory()`
- **Before:** `return bool(book.pdf_extras) or bool(book.cover_url)` — since Libro.fm always returns a `cover_url`, this was effectively always `True`
- **After:** `return bool(book.pdf_extras)` — only PDF extras trigger subdirectory at this level; covers are handled in `_resolve_output_dir()` with config awareness

### Bug 2: `_resolve_output_dir()` double-appended the title
- **File:** `librofm_downloader/downloader.py`
- **Function:** `_resolve_output_dir()`
- **Before:** Called `resolve_path(book)` which returns `"Author/Title"`, then appended `title_sanitized` again → `"Author/Title/Title"`
- **After:** Uses `resolve_path(book)` directly as the relative path — no extra title append
- **Also added:** Optional `config` parameter so that `download_covers=True` + `book.cover_url` can trigger subdirectory when covers will actually be downloaded

### Bug 3: Cover download used naked httpx client (no headers)
- **File:** `librofm_downloader/downloader.py`
- **Function:** `_download_cover()`
- **Before:** `httpx.Client(transport=transport, follow_redirects=True)` — no headers
- **After:** Adds `headers=LibroFmClient.DEFAULT_HEADERS` (`X-LibroFm-AppVer`, `User-Agent`) so CDN accepts requests

### Bug 4: Protocol-relative cover URLs rejected by httpx
- **File:** `librofm_downloader/downloader.py`
- **Function:** `_download_cover()`
- **Problem:** Libro.fm returns `//covers.libro.fm/978...jpg` — httpx raises "Request URL is missing an 'http://' or 'https://' protocol"
- **Fix:** Added normalization: `if url.startswith("//"): url = "https:" + url`

### Tests updated
- **File:** `tests/test_downloader.py`
- Renamed `test_true_when_cover_url_present` → `test_false_when_cover_url_only`
- Added `test_book_with_only_cover_does_not_create_subdirectory`
- Replaced config-gated cover tests with: `test_resolve_output_dir_flat_for_cover_only_without_config`, `test_resolve_output_dir_flat_for_cover_regardless_of_config`, `test_resolve_output_dir_subdir_no_title_doubling`
- Updated comments to reflect new semantics

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Covers should trigger subdirectory when `download_covers=True` + `cover_url` exists | User explicitly wants this behavior — cover sits alongside .m4b in a titled folder |
| Covers do NOT trigger subdirectory when `download_covers=False` | No extra files to store, so flat author-dir layout |
| `resolve_path()` already includes title — don't double it | `resolve_path()` returns `"Author/Series/Title"` or `"Author/Title"`; appending title again created the doubling |
| Keep `config` param on `_resolve_output_dir` rather than `needs_subdirectory` | Subdirectory decision needs both book data AND user config — cleaner to resolve at call site |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| Path doubling: `Author/Title/Title.m4b` | `resolve_path()` returns `Author/Title`, then code appended `title_sanitized` again | Removed extra append; use `resolve_path()` result directly |
| Every book got a subfolder | `needs_subdirectory()` checked `bool(cover_url)` — Libro.fm always returns one | Changed to only check `pdf_extras`; moved cover logic to `_resolve_output_dir` with config gating |
| Cover never downloaded (silent failure) | `_download_cover()` used bare `httpx.Client` without `X-LibroFm-AppVer` / `User-Agent` headers — CDN rejected request | Added `LibroFmClient.DEFAULT_HEADERS` to the client |
| `Failed to download cover from //covers.libro.fm/...` | Protocol-relative URL (`//host/path`) not accepted by httpx | Prepend `https:` when URL starts with `//` |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/downloader.py` | Fixed `needs_subdirectory()`, `_resolve_output_dir()` (no title doubling + config-aware cover gating), `_download_cover()` (headers + protocol-relative URL fix) |
| `tests/test_downloader.py` | Updated 6 tests for new semantics; added 2 new tests for title-doubling and flat-cover behavior |

## Open Items & Next Steps

- [ ] Re-run download for "This Story Might Save Your Life" to verify cover image appears in the subfolder
- [ ] Consider adding a test for protocol-relative URL normalization in `_download_cover`

---

*Log written by write-log skill*
