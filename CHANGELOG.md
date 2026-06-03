# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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

### Fixed
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
