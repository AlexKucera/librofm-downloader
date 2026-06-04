# Issue #26: Book Intake Module (`book.py` + `path.py`) Extraction

> **Date:** 2026-06-04
> **Type:** issue
> **Reference:** PRD 001 Candidate #2 — Deepen Architecture: Module Depth & Domain Alignment

## Goal

Extract the `Book` domain model and API-shape intake function from their scattered locations (`downloader.py` + `orchestrator.py`) into a dedicated `book.py`, and extract all path-resolution/sanitization logic into a dedicated `path.py`. This eliminates the monolithic `downloader.py` (652→~490 lines) and ensures **zero knowledge of raw Libro.fm API dict shape exists outside `book.py`** — a PRD success criterion.

## What Was Done

- **Created `librofm_downloader/book.py`** — New deep module owning:
  - `Book` frozen dataclass (11 fields: title, authors, narrators, isbn, series, series_num, cover_url, pdf_extras, publication_year/month/day)
  - `from_library_row(raw: dict) -> Book` intake function with ISBN str coercion, nested narrator resolution (`audiobook_info.narrators` → top-level fallback), PDF extras bool coercion, and default values
  - Full module docstring declaring ownership of all API-shape normalization

- **Created `librofm_downloader/path.py`** — New pure-logic module (no I/O, no network) owning:
  - `sanitize(component)` — filesystem-safe path component sanitization (5 rules: colon replacement, illegal char stripping, control char removal, trailing dot removal, 255-char cap)
  - `_ILLEGAL_CHARS` / `_CONTROL_CHARS` — character classification constants
  - `_TOKEN_REGISTRY` — 12 token → (attribute, formatter) mappings for custom patterns
  - `_token_value(book, token)` — single token resolution
  - `resolve_path(book, pattern)` — main entry point: custom pattern or default conditional logic
  - `_resolve_default_path(book)` — Author/Series/Book N Title conditional paths
  - `_resolve_custom_pattern(book, pattern)` — `{TOKEN}` regex substitution
  - `needs_subdirectory(book)` — PDF extras → True (cover_url is config-gated separately)
  - `_resolve_output_dir(book, output_base, config)` — full output directory resolution

- **Created `tests/test_book.py`** — 20 tests across 6 classes:
  - `TestFromLibraryRowComplete` — tracer bullet with all fields populated
  - `TestMissingFields` — empty dict → all defaults verified
  - `TestIsbnCoercion` — int→str coercion, string passthrough, missing default
  - `TestNarratorResolution` — audiobook_info priority, top-level fallback, both missing, no audiobook_info key
  - `TestPdfExtrasBoolCoercion` — True/False bool, truthy/falsy int, missing key, missing audiobook_info

- **Created `tests/test_path.py`** — 59 tests across ~18 classes:
  - Sanitization: illegal chars, colon replacement, control chars, trailing dots, whitespace trim, length cap, preserved chars, edge cases (empty, unicode)
  - Default path: series+number, series-only, standalone (no series)
  - Custom pattern: basic, override-default, ALL_AUTHORS, SERIES_NUM, ISBN, narrator tokens, publication date tokens, missing tokens, sanitization of output
  - Subdirectory decision: pdf_extras=True, cover_only=False, both=True, neither=False, defaults, truthy int
  - Output dir integration: subdir for pdf_extras, flat for cover-only (no config), subdir for cover+download_covers, no-title-doubling verification, flat for no extras, string base acceptance

- **Slimmed `librofm_downloader/downloader.py`** — Removed ~140 lines:
  - Removed: `Book` class, `sanitize()`, `_ILLEGAL_CHARS`, `_CONTROL_CHARS`, `_TOKEN_REGISTRY`, `_token_value()`, `resolve_path()`, `_resolve_default_path()`, `_resolve_custom_pattern()`, `needs_subdirectory()`, `_resolve_output_dir()`
  - Added imports from `book.py` and `path.py`
  - Updated module docstring to declare scope: "download engine only; path logic lives in path.py; Book lives in book.py"

- **Updated `librofm_downloader/orchestrator.py`** — Removed `_raw_to_book()` (21 lines); now imports `from_library_row` from `book.py` and calls it directly in `download_all_books()`

- **Updated `librofm_downloader/cli.py`** — Split import: `Book` from `book.py`, `download_book` from `downloader.py`

- **Updated `tests/test_downloader.py`** — Split imports: `Book` from `book.py`, path functions from `path.py`, download functions from `downloader.py`

- **Updated `tests/test_orchestrator.py`** — Import `Book` from `book.py`

- **Updated `tests/test_progress.py`** — Import `Book` from `book.py`; added explicit `download_m4b`, `download_zip_part`, `download_book` imports from `downloader.py` for inline test imports

- **Rewrote `CONTEXT.md`** — Replaced domain glossary with full extraction context document: file inventory, key code snippets, architecture diagrams, import graph, data flow, raw API shape, test inventory with per-class mapping, and start-here instructions

- **Committed `docs/prd/001-deepen-architecture-prd.md`** — 211-line PRD document defining all 6 module-deepening candidates, user stories, testing decisions, cross-cutting import migration table, and success criteria

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| `from_library_row()` naming (not `_raw_to_book`) | Public function name signals intent as the canonical intake point; underscore-prefixed name in orchestrator suggested private implementation detail |
| Path helpers in separate `path.py` (not folded into `book.py`) | PRD explicitly separates concerns: book.py = domain model + API intake; path.py = output structure planning foundation. Keeps both modules under 5 public symbols (depth metric) |
| No backward-compat re-exports in `downloader.py` | All 6 importing files updated in same commit; no external consumers exist. Clean break preferred over deprecation cycle for internal-only code |
| `needs_subdirectory()` does NOT consider `cover_url` | Cover-gated subdirectory is a config-aware decision in `_resolve_output_dir()`. `needs_subdirectory()` stays pure (book-only) so it's testable without Config |
| Keep `_resolve_output_dir()` in `path.py` (not move to future `OutputPlan`) | It's path logic, not download logic. When OutputPlan is built (PRD Candidate #3), this function will be its foundation |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| None | Extraction was clean — all symbols had clear ownership boundaries, no circular dependencies introduced | N/A |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/book.py` | **NEW** — Book frozen dataclass + `from_library_row()` intake function (54 lines) |
| `librofm_downloader/path.py` | **NEW** — sanitize, resolve_path, needs_subdirectory, _resolve_output_dir, token registry (159 lines) |
| `tests/test_book.py` | **NEW** — 20 tests across 6 classes for Book + from_library_row() edge cases |
| `tests/test_path.py` | **NEW** — 59 tests across ~18 classes for all path functions |
| `librofm_downloader/downloader.py` | Removed ~140 lines of extracted code; imports from book.py + path.py; updated docstring |
| `librofm_downloader/orchestrator.py` | Removed `_raw_to_book()`; imports + calls `from_library_row()` from book.py |
| `librofm_downloader/cli.py` | Split import: Book from book.py, download_book from downloader.py |
| `tests/test_downloader.py` | Split imports across book.py, path.py, downloader.py |
| `tests/test_orchestrator.py` | Import Book from book.py |
| `tests/test_progress.py` | Import Book from book.py; explicit downloader imports for inline usage |
| `CONTEXT.md` | Rewrote as extraction context document (224 lines) |
| `docs/prd/001-deepen-architecture-prd.md` | **NEW** — PRD for full 6-candidate deepening plan (211 lines) |

## Open Items & Next Steps

- [ ] **Commit all changes** — 4 new files + 7 modified files currently uncommitted (git status shows `??` and ` M`)
- [ ] **PRD Candidate #3: Output Structure Planning** — Build `OutputPlan` dataclass + `resolve_output_plan()` on top of the newly extracted `path.py`
- [ ] **PRD Candidate #6: Libro.fm Session** — Rename `LibroFmClient` → `LibroFmSession`, constructor injection, transport removal from endpoint signatures
- [ ] **PRD Candidate #4: Download Attempt** — Slim `download_book()` from 9 params to 4 (book, session, plan, reporter); introduce `DownloadResult` dataclass
- [ ] **PRD Candidate #5: Download Reporting** — Bound callable from `start_download()`, internal task identity
- [ ] **PRD Candidate #1: Sync Run Pipeline** — Extract `sync_run()` from cli.py; slim CLI to ≤80 lines
- [ ] Verify all 338 tests pass after commit (3 known Ctrl+C hang tests excluded)

---

*Log written by write-log skill*
