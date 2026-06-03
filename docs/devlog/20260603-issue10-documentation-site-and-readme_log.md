# Project Documentation Site and GitHub README — Issue #10

> **Date:** 2026-06-03
> **Type:** issue
> **Reference:** [Issue #10](https://github.com/AlexKucera/librofm-downloader/issues/10)

## Goal

Build a complete MkDocs documentation site in `docs/` and polish the GitHub README.md — the final slice making the project usable, discoverable, and well-documented. All code snippets must match the actual implementation from slices 1–6b.

## What Was Done

### MkDocs site (8 pages + config)

- **`docs/mkdocs/mkdocs.yml`** — Material theme with deep purple/amber palette, light/dark toggle, navigation tabs, code copy, TOC follow. Markdown extensions: admonition, highlight, superfences, tabbed, tables. Fixed pre-existing typo (`pymxdownx.tabbed` → `pymdownx.tabbed`). Set `use_directory_urls: false`, `site_dir: ../../docs/html`.
- **`docs/mkdocs/index.md`** — Landing page with Python 3.11+ badge, GPL-3.0 badge, one-paragraph description, feature list (8 bullets), 3-step quickstart, docs link table.
- **`docs/mkdocs/quickstart.md`** — Install (PyPI + source), configure (`config.yaml` + `secrets.yaml` with full examples), run (basic sync, TTY output example, non-TTY/cron output example, "nothing new" message), output directory structure tree.
- **`docs/mkdocs/configuration.md`** — File locations, secrets.yaml schema (2 fields), config.yaml schema (4 fields with types/defaults), full/minimal YAML examples, deep-merge explanation, validation error table (3 errors with fixes), download_history.json format and behavior.
- **`docs/mkdocs/secrets.md`** — Purpose, file format, why it's gitignored, 4 common mistakes (credentials in config, committed-before-gitignore, missing fields, wrong indentation), security notes (plaintext storage, HTTPS-only, 2FA note).
- **`docs/mkdocs/path-patterns.md`** — Default conditional logic (3 cases: standalone, series+num, series-no-num), subdirectory logic rules, full token registry table (12 tokens with source/example/notes), custom pattern setup, 4 pattern examples (flat-by-author, by-series, by-narrator, ISO-date-prefix), path sanitization rules (6 steps).
- **`docs/mkdocs/format-strategies.md`** — Overview table of 3 strategies, detailed sections for each (flow, output examples, when-to-use), decision flowchart, technical details for M4B downloads (8MB chunks, .partial→atomic rename, resume via Range) and MP3 downloads (manifest→ZIP parts→extract→cleanup).
- **`docs/mkdocs/cli-usage.md`** — Synopsis, options table (5 flags), `--verbose` output example, `--limit` explanation, exit codes (0/1/130) with scenarios, cron examples (3: basic daily, email-on-failure, weekly-with-limit), systemd timer unit files, TTY vs non-TTY auto-detection with output comparison.
- **`docs/mkdocs/troubleshooting.md`** — 12 issues across 6 categories: auth failures (401, non-401), config errors (credentials-in-config, missing-fields, invalid-format, file-not-found), download issues (interrupted/resume, per-book-failure, m4b_only-skip), history problems (corrupt-json, re-downloading), output/path issues (wrong-dir, permission-denied), performance (slow-downloads, large-library), getting-help checklist.

### README.md

- **`README.md`** — Rewritten with badges (Python 3.11+, GPL-3.0), description, feature list, quickstart code block, documentation page table (7 pages linked), format strategies comparison table, path customization blurb, "lightweight alternative to Kotlin Docker container" comparison note.

### Build infrastructure

- Installed mkdocs, mkdocs-material, pymdown-extensions into venv
- Restructured: moved all `.md` source files + `mkdocs.yml` + `stylesheets/` into `docs/mkdocs/` so that `site_dir` (`docs/html/`) is outside `docs_dir`
- Built HTML output to `docs/html/` with flat URLs (`use_directory_urls: false`) — pages are e.g., `configuration.html` not `configuration/index.html`

## Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Material theme over readthedocs | Cleaner default look, built-in dark mode toggle, better navigation UX |
| Source in `docs/mkdocs/`, build to `docs/html/` | MkDocs refuses `site_dir` inside `docs_dir` (recursive copy risk). User explicitly requested this layout |
| `use_directory_urls: false` | User requested flat `.html` filenames instead of directory-based URLs |
| Code snippets verified against actual source | Every YAML example, CLI flag, exit code, token name, API endpoint, and error message cross-checked against `cli.py`, `config.py`, `client.py`, `downloader.py`, `history.py`, `progress.py` |
| LICENSE badge links to GitHub | `LICENSE.md` is outside `docs_dir`; relative link `../LICENSE.md` wouldn't resolve in built HTML; GitHub blob URL works universally |

## Gotchas & Fixes

| Problem | Root Cause | Fix |
|---------|------------|-----|
| `pymxdownx.tabbed` typo in existing mkdocs.yml | Pre-existing typo from earlier scaffolding | Corrected to `pymdownx.tabbed` |
| `mkdocs build -d docs/html/` refused | `site_dir` cannot be inside `docs_dir` — MkDocs detects this as recursive copy risk | Moved source files to `docs/mkdocs/`, set `docs_dir: .` and `site_dir: ../../docs/html` relative to `docs/mkdocs/` |
| Initial build to `/tmp/` then `cp -R` worked but user wanted proper structure | User explicitly asked for `docs/mkdocs/` source + `docs/html/` output layout | Restructured per user request |
| LICENSE.md link warning in build | Relative path `../LICENSE.md` resolved outside `docs_dir` | Changed to absolute GitHub URL |

## Files Changed

| File | Change Summary |
|------|---------------|
| `docs/mkdocs/mkdocs.yml` | MkDocs config — Material theme, nav, extensions, `use_directory_urls: false`, `site_dir: ../../docs/html`. Fixed `pymdownx` typo. |
| `docs/mkdocs/index.md` | Docs landing page — badges, features, quickstart, doc links |
| `docs/mkdocs/quickstart.md` | Install/config/run walkthrough with TTY + non-TTY output examples |
| `docs/mkdocs/configuration.md` | Full schema reference for config.yaml, secrets.yaml, history JSON |
| `docs/mkdocs/secrets.md` | Why secrets.yaml exists, 4 common mistakes, security notes |
| `docs/mkdocs/path-patterns.md` | 12 tokens, default logic, 4 custom pattern examples, sanitization rules |
| `docs/mkdocs/format-strategies.md` | 3 format strategies with flows, outputs, decision guide, technical details |
| `docs/mkdocs/cli-usage.md` | 5 CLI flags, 3 exit codes, 3 cron examples, systemd unit, TTY vs non-TTY |
| `docs/mkdocs/troubleshooting.md` | 12 issues across 6 categories with cause/fix for each |
| `README.md` | Polished README — badges, features, quickstart, docs table, format comparison, alt-project note |
| `docs/stylesheets/extra.css` | Moved into `docs/mkdocs/` (unchanged content) |
| `docs/html/` | Built HTML output (16 items, flat `.html` URLs) |

## Open Items & Next Steps

- None — Issue #10 acceptance criteria fully met:
  - ✅ `mkdocs.yml` with working configuration
  - ✅ `mkdocs build` succeeds without errors
  - ✅ Quickstart, Configuration Reference, Path Patterns, Format Strategies, CLI Usage, Troubleshooting pages all present
  - ✅ Secrets page included
  - ✅ README.md polished with badges, description, features, quickstart, docs link
  - ✅ All code snippets verified against actual implementation (172 tests still pass)

---

*Log written by write-log skill*
