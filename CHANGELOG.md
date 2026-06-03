# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- MP3 format fallback: download manifest fetch, ZIP part download+extraction
  with .partial tracking and resume, format strategy selector (m4b_mp3_fallback,
  mp3_only, m4b_only), and `--limit` CLI flag for capped downloads
- M4B download pipeline: streaming chunked download with .partial files,
  atomic rename to .m4b, resume support via HTTP Range header
- `fetch_m4b_url()` client method for M4B download URL lookup
- `download_book()` orchestration: resolve path → query M4B → download →
  write history; returns None when book has no M4B available
- Full CLI download loop with per-book status, summary counts, and --verbose
  flag showing config/auth/library/download details
- `config.yaml` template and `secrets.yaml` gitignored credentials file
- 12 new tests covering M4B query, streaming download, resume, path
  integration, subdirectory logic, history post-download, skip behavior,
  and verbose output (109 total)
- PDF extras and cover art download: `fetch_pdf_extra_url()` client
  endpoint, `download_accompanying_files()` with config toggles
  (`download_extras`, `download_covers`), streaming .partial → atomic
  rename pattern, non-critical failure handling (warnings only), and
  output structure verification (subdirectory vs flat layout)
- TTY-aware download reporting: rich progress bars with live %/ETA/speed/
  file size for interactive terminals, plain log lines for pipes/cron,
  Content-Length-driven total so percentage works from first chunk,
  per-book failure isolation (one failed book doesn't stop batch),
  and fatal error immediate-exit before download loop starts
- 12 new tests covering PDF URL fetch, cover/PDF download, .partial
  cleanup, config toggle behavior, failure handling, and directory layout
  (134 total)

- Enhanced summary: failed books listed with ISBN/title/reason, skipped
  books listed with ISBN/title; both plain-text and rich/TTY reporters
- Graceful Ctrl+C handling: clean shutdown message instead of traceback,
  exit code 130 (standard Unix SIGINT convention)
- 3 integration tests exercising full run() pipeline: happy path,
  mixed result (download/skip/fail), fatal auth failure
- 12 new tests covering enhanced summary formatting, exit code semantics,
  graceful shutdown, and integration scenarios (168 total)

### Fixed
- **downloader:** Path doubling: `resolve_path()` returns Author/Title but code
  appended title again, producing nested folders like Title/Title/Title.m4b.
  Also fix cover download: add Libro.fm headers to httpx client, normalize
  protocol-relative URLs (//cdn → https://cdn)
- Library endpoint key mismatch: API returns "audiobooks" not "books"
- M4B endpoint key mismatch: API returns "m4b_url" not "url"
- Narrators nested under `audiobook_info.narrators` in API response
- ISBN type mismatch in history lookup: JSON keys are strings but API
  returns ISBN as integer — added str() coercion in find/is_downloaded
- Missing download loop in CLI run() function (listed books but never downloaded)

### Changed
- Initial project scaffolding: pyproject.toml, package structure, test suite
- Config module with YAML loading, secrets deep-merge, validation, and defaults
- OAuth2 client with password grant auth and paginated library fetch
- Download history tracking with corrupt JSON recovery
- Path resolution with default conditional patterns and custom token substitution
- Filesystem-safe component sanitization (illegal chars, control chars, colons)
- Immutable Book dataclass for typed book metadata
- Subdirectory decision logic based on PDF extras or cover art presence
