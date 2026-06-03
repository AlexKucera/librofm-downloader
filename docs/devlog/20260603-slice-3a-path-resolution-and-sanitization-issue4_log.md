# Slice 3a: Path Resolution + Sanitization

> **Date:** 2026-06-03
> **Type:** slice
> **Reference:** [Issue #4](https://github.com/AlexKucera/librofm-downloader/issues/4)

## Goal

Build a pure logic module for resolving output file paths from book metadata and sanitizing components for filesystem safety. No I/O, no network — all deterministic string manipulation.

## What Was Done

### 1. `Book` dataclass (`librofm_downloader/downloader.py`)
- **`@dataclass(frozen=True) Book`** — immutable record with fields: `title`, `authors`, `narrators`, `isbn`, `series`, `series_num`, `cover_url`, `pdf_extras`, `publication_year/month/day`
- All metadata needed for path resolution and subdirectory decisions in one typed, immutable container

### 2. `sanitize(component)` function
Pure string sanitization with 5 rules applied in order:
1. Replace `:` → ` -`
2. Strip `< > / \ | ? *` via `str.translate()` + control chars U+0000–U+001F
3. Trim whitespace (before dot removal so exposed dots are caught)
4. Remove trailing dots (`rstrip(".")`)
5. Cap at 255 characters

Preserves: dashes, commas, apostrophes, parentheses, internal periods.

### 3. `resolve_path(book, pattern=None)` function
- **Default mode** (no pattern): conditional logic based on series presence:
  - series + series_num → `{Author}/{Series}/Book N {Title}`
  - series only → `{Author}/{Series}/{Title}`
  - no series → `{Author}/{Title}`
- **Custom mode** (pattern set): token substitution via regex `\{([A-Z_]+)\}` with 11 supported tokens: `FIRST_AUTHOR`, `ALL_AUTHORS`, `SERIES_NAME`, `SERIES_NUM`, `BOOK_TITLE`, `ISBN`, `FIRST_NARRATOR`, `ALL_NARRATORS`, `PUBLICATION_YEAR/MONTH/DAY`
- Every component sanitized after substitution
- Token registry pattern: `_TOKEN_REGISTRY` dict maps token names to `(attribute, formatter)` tuples; `_token_value()` resolves each token

### 4. `needs_subdirectory(book)` function
- Returns `True` when `book.pdf_extras` is truthy OR `book.cover_url` is non-empty
- Returns `False` otherwise (standalone audiobook file as leaf node)

### Test Suite (56 new tests across 10 test classes)

| Class | Tests | What's Verified |
|-------|-------|-----------------|
| `TestSanitizeIllegalChars` | 6 | `< > / \ | ? *` stripped |
| `TestSanitizeColonReplacement` | 3 | `:` → ` -`, including combined with illegal chars |
| `TestSanitizeControlChars` | 5 | Null, tab, newline, CR, range U+01–U+1E stripped |
| `TestSanitizeTrailingDots` | 4 | Single/multiple dots removed, internal preserved, trim-then-strip order |
| `TestSanitizeTrimWhitespace` | 4 | Leading/trailing/internal space handling |
| `TestSanitizeLengthCap` | 3 | Short unchanged, >255 capped, exact 255 unchanged |
| `TestSanitizePreservedChars` | 6 | Dashes, commas, apostrophes, parentheses, periods, combined safe+unsafe |
| `TestSanitizeEdgeCases` | 5 | Empty string, all-illegal, whitespace-only, unicode, unicode+illegal |
| `TestDefaultPath*` (3 classes) | 5 | Series+num, series-only, no-series paths with sanitization |
| `TestCustomPathPattern` | 10 | All 11 tokens, override behavior, missing tokens, sanitization |
| `TestNeedsSubdirectory` | 5 | PDF extras, cover art, both, neither, defaults |

**Total: 97 tests** (41 existing + 56 new) — all passing

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| `@dataclass(frozen=True)` for Book | Immutable records prevent accidental mutation; same pattern as Config and HistoryEntry |
| `resolve_path(book, pattern=None)` as single function | Simple, testable, follows existing patterns in codebase. Optional `pattern` param avoids needing a class |
| Token registry dict pattern | Declarative mapping of tokens to (attr, formatter) pairs makes adding new tokens trivial — just add one line to `_TOKEN_REGISTRY` |
| Regex-based token substitution (`\{([A-Z_]+)\`) | Simple, handles any ordering of tokens, unknown tokens produce empty string (not error) |
| Trim before trailing-dot removal | `"  filename.  "` must become `"filename"`, not `"filename."`. Discovered via failing test |
| `str.translate()` for illegal char stripping | O(n) single-pass character deletion; faster than repeated `str.replace()` calls |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| Test expectation error: `"O'Brien, Brandon - Author"` vs actual `"O'Brien, Brandon Author"` | Test author assumed colon was in author name `"O'Brien, Brandon <Author>"` but there's no colon there — only angle brackets and comma | Fixed test expectation to match actual behavior |
| Trailing dot not removed after whitespace trim | Original implementation ordered: strip dots → trim whitespace. Input `"  filename.  "` → strip dots → `"  filename  "` → trim → `"filename."` (dot exposed by trim but already processed) | Swapped order: trim → strip dots. Added `test_trailing_dot_after_whitespace_trim` to catch this |
| `import re` inside function body | Initial implementation placed import inside `_resolve_custom_pattern` for laziness | Moved to module-level import per Python best practices |

## Files Changed

| File | Change Summary |
|------|---------------|
| `librofm_downloader/downloader.py` | **New** — Book dataclass, sanitize(), resolve_path(), needs_subdirectory(), token registry (~130 lines) |
| `tests/test_downloader.py` | **New** — 56 tests across 11 classes covering all sanitization rules, default paths, custom tokens, subdirectory logic |

## Acceptance Criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Default path resolves correctly for book with series + series_num | ✅ `test_basic_series_with_number` |
| 2 | Default path resolves correctly for book with series but no series_num | ✅ `test_basic_series_no_number` |
| 3 | Default path resolves correctly for book without series | ✅ `test_standalone_book` |
| 4 | Custom path_pattern with token substitution works for all documented tokens | ✅ 11 tokens tested across 7 tests |
| 5 | Custom path_pattern overrides default when set | ✅ `test_custom_pattern_overrides_default` |
| 6 | Colons replaced with `-` in all components | ✅ 3 tests in `TestSanitizeColonReplacement` |
| 7 | Illegal chars stripped: `< > / \ | ? *` | ✅ 6 tests in `TestSanitizeIllegalChars` |
| 8 | Control characters stripped | ✅ 5 tests in `TestSanitizeControlChars` |
| 9 | Trailing dots removed | ✅ 4 tests in `TestSanitizeTrailingDots` |
| 10 | Whitespace trimmed | ✅ 4 tests in `TestSanitizeTrimWhitespace` |
| 11 | Components capped at 255 chars | ✅ 3 tests in `TestSanitizeLengthCap` |
| 12 | Dashes, commas, apostrophes, parentheses preserved | ✅ 6 tests in `TestSanitizePreservedChars` |
| 13 | Subdirectory-needed returns True when PDF extras or cover art present | ✅ 3 tests in `TestNeedsSubdirectory` |
| 14 | Subdirectory-needed returns False when neither present | ✅ 2 tests in `TestNeedsSubdirectory` |
| 15 | ~20 tests covering all path patterns, every sanitization rule, edge cases | ✅ **56 tests** (nearly 3× target) |
| 16 | All tests pass | ✅ **97/97 passed** |

**16/16 AC met** ✅

## Open Items & Next Steps

- This slice builds pure logic only — no file system operations
- Next slices would wire this into the download pipeline: resolve paths before downloading, create subdirectories when `needs_subdirectory()` returns True
- The `Config` dataclass doesn't have a `path_pattern` field yet — that would be added when wiring custom patterns from config into `resolve_path()`

---
*Log written by write-log skill*
