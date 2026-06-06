# Issue #47: Interactive Book Selection — selector.py Module

> **Date:** 2026-06-06
> **Type:** issue
> **Reference:** [GitHub #47](https://github.com/AlexKucera/librofm-downloader/issues/47)

## Goal

Create `librofm_downloader/selector.py` with `select_books(books) -> list[Book]` — an interactive checkbox prompt using `questionary` that lets users pick which books to download. Includes `_format_row(book, index) -> str` helper for display formatting.

## What Was Done

- Added `questionary>=2.1.1` to `dependencies` in `pyproject.toml`
- Created `librofm_downloader/selector.py` with two functions:
  - `_format_row(book, index)` — formats Book into `"N. Title — Author [Series #N]"` display string
  - `select_books(books)` — opens questionary checkbox (all unchecked by default), zero-selection message, confirmation summary + y/N prompt, returns selected Books in original input order
- Created `tests/test_selector.py` with 9 TDD tests covering all acceptance criteria
- Used `unsafe_ask()` on the checkbox to propagate `KeyboardInterrupt` (instead of `.ask()` which catches it and returns `None`)

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Use `unsafe_ask()` for checkbox, `.ask()` for confirm | `questionary.Question.ask()` catches `KeyboardInterrupt` and returns `None`. Issue requires Ctrl+C during checkbox to propagate upstream to `sync_run`. Confirm prompt can safely swallow Ctrl+C (returns `None` → falsy → empty list). |
| Map display rows → Book via dict lookup | `questionary.checkbox().ask()` returns the choice strings, not indices. Build a `row_to_book` dict to map chosen strings back to Book objects. |
| Return in original input order via `id(b)` set | User may toggle checkboxes in any order. Filter original list by `id(b) in selected_set` to preserve input ordering. |
| Pin `questionary>=2.1.1` (not `>=1.10`) | `questionary 2.1.0` crashes with `prompt_toolkit>=3.0.50` due to `_fix_unecessary_blank_lines` accessing changed internal layout API (`VSplit.content` removed). Fixed in 2.1.1. |
| Test via `mock.patch("librofm_downloader.selector.questionary")` | Patch at the import site, not globally. Mock `checkbox().unsafe_ask()` and `confirm().ask()` return values to avoid real TUI rendering. Test external behavior (inputs→outputs), not which questionary methods were called. |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| `AttributeError: 'VSplit' object has no attribute 'content'` on interactive test | `questionary 2.1.0` incompatible with `prompt_toolkit>=3.0.50`. Internal `_fix_unecessary_blank_lines` accesses removed `VSplit.content` attribute. | Upgraded to `questionary>=2.1.1`, pinned in `pyproject.toml` |
| Test mock returned `["C", "A"]` but impl expected formatted row strings | Mock values must match what `questionary.checkbox().unsafe_ask()` actually returns — the choice strings as provided to `choices=` parameter. | Changed mock to return `["3. C — Author", "1. A — Author"]` matching `_format_row` output |
| 11 pre-existing failures in `test_path.py` | `Config.__init__()` missing `rename_chapters` argument — unrelated to this issue | Not addressed (pre-existing, out of scope) |

## Files Changed

| File | Change Summary |
|------|---------------|
| `pyproject.toml` | Added `questionary>=2.1.1` to `dependencies` |
| `librofm_downloader/selector.py` | New module: `_format_row()` + `select_books()` |
| `tests/test_selector.py` | New test file: 9 tests (3 formatting + 6 selection flow) |

## Open Items & Next Steps

- [ ] Wire `select_books()` into `sync_run.py` pipeline (guarded by `--select` flag) — future issue
- [ ] 11 pre-existing `test_path.py` failures need fixing (Config missing `rename_chapters`)
- [ ] User interactive testing still pending (TUI requires real terminal)

---

*Log written by write-log skill*
