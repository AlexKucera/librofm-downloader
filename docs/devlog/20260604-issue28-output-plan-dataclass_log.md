# Issue #28: Output Structure Planning — OutputPlan Dataclass

> **Date:** 2026-06-04
> **Type:** issue
> **Reference:** [Issue #28](https://github.com/AlexKucera/librofm-downloader/issues/28)
> **Parent:** [#25 — PRD 001: Deepen Architecture](https://github.com/AlexKucera/librofm-downloader/issues/25)

## Goal

Introduce an `OutputPlan` frozen dataclass that carries all resolved paths and download flags for one Book. Add `resolve_output_plan()` function. Update download functions to consume plan fields instead of computing paths internally.

## What Was Done

### TDD Cycle — Vertical Slices (Red → Green → Refactor)

**Planning phase (scout):** Explored path.py (159 lines), book.py (Book dataclass), config.py (Config fields), downloader.py (486 lines). Key finding: `_resolve_output_dir()` only resolved the directory; audio filename `sanitize(title).m4b` was computed inline **twice** in `download_book()` (lines 252 & 279); cover/PDF filenames derived inside low-level download functions. No single object represented "all output paths for this book."

**User decisions confirmed:**
- Full file paths on OutputPlan (not dir + derive filenames)
- `format_strategy` stays separate from OutputPlan (it's a behavior flag, not a path concern)
- Happy-path-first test ordering

**Tracer Bullet #1 — RED→GREEN:**
- RED: Wrote `test_happy_path_all_enabled` → `ImportError: cannot import name 'OutputPlan'`
- GREEN: Implemented `OutputPlan` frozen dataclass + `resolve_output_plan()` in path.py → **64/64 pass**

**Incremental loop — 9 additional tests (all GREEN on first attempt):**
- Custom output pattern via `{TOKEN}` substitution
- Cover disabled (`download_covers=False`) → `cover_path=None`
- PDF disabled (`download_extras=False`) → `pdf_path=None`
- No `cover_url` on book → `cover_path=None` (data gate)
- No `pdf_extras` on book → `pdf_path=None` (data gate)
- String `output_base` accepted (type flexibility)
- Subdirectory layout when `pdf_extras=True`
- Flat layout when no extras
- `OutputPlan` is frozen (immutable)

**Refactor phase — Wired OutputPlan into downloader.py:**
- `download_book()` now calls `resolve_output_plan()` instead of `_resolve_output_dir()`, uses `plan.audio_path`
- Eliminated duplicated `sanitize(title).m4b` computation (was at 2 locations, lines 252 & 279)
- `download_accompanying_files()` signature changed from `output_dir: Path|str` → `plan: "OutputPlan"`
- `_download_cover()` and `_download_pdf()` gained optional `expected_path` parameter for validation
- Updated all call sites (3 in `download_book`, 7 test methods in `test_downloader.py`)
- Made `config` optional on `resolve_output_plan()` (`Config | None = None`) to handle graceful degradation

## Decisions & Rationale

| Decision | Rationale |
|-----------|-----------|
| OutputPlan carries full file Paths (not just directories) | Downloaders receive exact output paths — zero path computation inside download functions. Cleaner separation of concerns. |
| `format_strategy` excluded from OutputPlan | It's a download behavior flag (which strategy to use), not an output path concern. Keeps OutputPlan focused on "where things go." |
| Config is optional (`None` default) on `resolve_output_plan()` | Allows flexible usage; when no config, cover/pdf paths are simply `None`. No need for dummy config objects in tests or non-config contexts. |
| `_resolve_output_dir()` kept as internal helper | Still used by `resolve_output_plan()`. Removing it would force duplication of subdirectory logic. It's now effectively private implementation detail. |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| No significant gotchas this session | Initial implementation handled all edge cases correctly from first GREEN phase | N/A — 9 incremental tests all passed without code changes |

**Minor note:** During refactor phase, worker made `config` optional on `resolve_output_plan()` so downstream callers don't need to construct a dummy Config when only audio path is needed.

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/path.py` | +63 lines: `OutputPlan` frozen dataclass (4 fields) + `resolve_output_plan()` function. Imports `dataclass`. |
| `librofm_downloader/downloader.py` | Refactored: `download_book()` consumes `plan.audio_path`; `download_accompanying_files()` takes `plan: OutputPlan`; `_download_cover()`/`_download_pdf()` accept `expected_path`. Eliminated duplicated audio-path computation. |
| `tests/test_path.py` | +59 lines: `TestResolveOutputPlan` class with 10 tests covering happy path, custom pattern, disabled flags, data gates, string base, subdirectory/flat layouts, frozen immutability. |
| `tests/test_downloader.py` | Updated 7 test methods: `download_accompanying_files()` calls now create and pass `OutputPlan`; assertions reference `plan.cover_path` / `plan.pdf_path`. |

## Acceptance Criteria Report

| # | Criterion | Status |
|---|-----------|--------|
| 1 | `OutputPlan` is a frozen dataclass with all fields documented | ✅ PASS — 4 fields: `audio_path`, `partial_path`, `cover_path` (\| None), `pdf_path` (\| None), each with doc comments |
| 2 | `resolve_output_plan()` produces correct paths for default/custom/subdirectory/flat/disabled patterns | ✅ PASS — 10 tests in `TestResolveOutputPlan` |
| 3 | Download functions consume plan fields; no path computation inside download functions | ✅ PASS — `plan.audio_path`, `plan.cover_path`, `plan.pdf_path` used throughout |
| 4 | All existing path-related tests pass; new edge case tests | ✅ PASS — 73 path tests + 88 downloader tests = 161 pass, 0 regressions |
| 5 | `path.py` total public symbols ≤12 | ✅ PASS — 5 owned symbols: `sanitize`, `resolve_path`, `needs_subdirectory`, `OutputPlan`, `resolve_output_plan` |

## Test Count Summary

| Suite | Before | After | Delta |
|-------|--------|-------|-------|
| `test_path.py` | 63 | 73 | **+10** |
| `test_downloader.py` | 88 | 88 | ±0 (call sites updated) |
| All other suites | 76 | 76 | unchanged |
| **Total** | **227** | **237** | **+10 new tests** · **ALL PASS** |

## Open Items & Next Steps

- [ ] Issue #28 is complete. Ready for next issue in the #25 PRD roadmap.
- [ ] Consider adding `output_pattern` Config field to wire custom token patterns through config (currently `resolve_path(book, pattern=...)` supports patterns but no Config field / CLI flag exists)
- [ ] Run `npx gitnexus analyze` to refresh index after these structural changes

---

*Log written by write-log skill*
