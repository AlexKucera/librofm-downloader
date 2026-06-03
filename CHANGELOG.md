# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project scaffolding: pyproject.toml, package structure, test suite
- Config module with YAML loading, secrets deep-merge, validation, and defaults
- OAuth2 client with password grant auth and paginated library fetch
- Download history tracking with corrupt JSON recovery
- CLI skeleton wiring config → auth → library → filter → print
- Path resolution with default conditional patterns and custom token substitution
- Filesystem-safe component sanitization (illegal chars, control chars, colons)
- Immutable Book dataclass for typed book metadata
- Subdirectory decision logic based on PDF extras or cover art presence
