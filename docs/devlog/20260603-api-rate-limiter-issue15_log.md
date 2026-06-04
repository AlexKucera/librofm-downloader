# API Rate Limiter — Issue #15

> **Date:** 2026-06-03
> **Type:** issue
> **Reference:** [Issue #15](https://github.com/AlexKucera/librofm-downloader/issues/15)

## Goal

Implement a lightweight API rate limiter using `threading.Semaphore(3)` that caps concurrent Libro.fm API calls regardless of worker count. CDN file downloads must NOT be limited.

## What Was Done

- Added `threading.Semaphore(3)` to `LibroFmClient.__init__` via `_api_semaphore` attribute
- Added `API_SEMAPHORE_CAPACITY = 3` configurable constant (not user-facing)
- Wrapped 3 API methods with `with self._api_semaphore:` context manager:
  - `fetch_m4b_url()` — M4B URL lookup
  - `fetch_download_manifest()` — MP3 manifest fetch
  - `fetch_pdf_extra_url()` — PDF extra URL lookup
- NOT applied to: `authenticate()`, `fetch_library()`, CDN downloads (`download_m4b`, `download_zip_part`)
- Added 4 new tests in `TestApiRateLimiter` class:
  1. `test_semaphore_blocks_at_capacity` — 4 threads, max 3 in-flight
  2. `test_semaphore_releases_on_exception` — semaphore released on `M4BUnavailableError`
  3. `test_cdn_downloads_bypass_semaphore` — CDN proceeds while API slots occupied
  4. `test_authenticate_and_fetch_library_not_limited` — auth/library work while slots full
- **198 total tests pass** (194 existing + 4 new)

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Semaphore on `LibroFmClient` (not external wrapper) | Encapsulates rate-limiting in the client; callers don't need to know about it. Cleanest fit since all 3 methods are on the same class |
| `with self._api_semaphore:` (context manager) | Guarantees release on both success and exception — no try/finally needed |
| Capacity = 3 (configurable constant) | Conservative default for Libro.fm API; not user-facing per issue spec |
| Not applied to `authenticate()`/`fetch_library()` | These happen before the parallel download phase (sequential), so no contention risk |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| `threading.Value` AttributeError in tests | `Value` is from `multiprocessing`, not `threading`. Used it for shared thread state initially | Switched to `dict + threading.Lock` for shared mutable state, or plain list for sequential tests |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/client.py` | Added `import threading`, `API_SEMAPHORE_CAPACITY` constant, `_api_semaphore` to `__init__`, wrapped 3 methods with `with self._api_semaphore:` |
| `tests/test_client.py` | Added `TestApiRateLimiter` class with 4 tests covering capacity blocking, exception release, CDN bypass, and non-limited method isolation |

## Open Items & Next Steps

- None — issue complete, all acceptance criteria met

---
*Log written by write-log skill*
