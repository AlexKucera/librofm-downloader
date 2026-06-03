# librofm-downloader

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-green.svg)](LICENSE.md)

**Download owned audiobooks from your Libro.fm account** — a lightweight, dependency-minimal CLI tool written in Python.

No Docker. No JVM. Just `pip install` and go.

## Features

- **Full library sync** — fetches every audiobook in your Libro.fm account with automatic pagination
- **M4B + MP3 formats** — downloads M4B (single file) or MP3 (ZIP parts extracted) with automatic fallback
- **Resume support** — interrupted downloads pick up where they left off via `.partial` files
- **Cover art & PDF extras** — optional download of cover images and accompanying PDFs
- **Customizable output paths** — token-based patterns for organizing your library on disk
- **TTY-aware progress** — rich progress bars in your terminal, clean log lines in cron jobs
- **Download history** — tracks what's been downloaded so re-runs only fetch new books
- **Graceful failure isolation** — one failed book doesn't stop the rest
- **Parallel downloads** — `ThreadPoolExecutor` downloads multiple books simultaneously; configurable via `--workers N` (default 3)

## Quick Start

```bash
# 1. Install
pip install librofm-downloader

# 2. Configure
cat > config.yaml << 'EOF'
librofm:
  format: m4b_mp3_fallback
  output_dir: ./audiobooks
  download_extras: true
  download_covers: true
EOF

cat > secrets.yaml << 'EOF'
librofm:
  username: your-email@example.com
  password: your-password
EOF

# 3. Run
librofm-downloader            # default: 3 parallel workers
librofm-downloader -w 5      # 5 parallel workers
librofm-downloader --workers 1  # sequential (1 worker)
```

## Documentation

Full documentation is available at [**docs/**](docs/) (built with MkDocs):

| Page | What it covers |
|------|---------------|
| [Quickstart](docs/quickstart.md) | Install, configure, run your first sync |
| [Configuration Reference](docs/configuration.md) | Every `config.yaml` / `secrets.yaml` field |
| [Secrets](docs/secrets.md) | Why credentials are separate, common mistakes |
| [Path Patterns](docs/path-patterns.md) | All tokens, default behavior, custom examples |
| [Format Strategies](docs/format-strategies.md) | `m4b_mp3_fallback` vs `mp3_only` vs `m4b_only` |
| [CLI Usage](docs/cli-usage.md) | Flags, exit codes, cron setup, TTY vs non-TTY |
| [Troubleshooting](docs/troubleshooting.md) | Common errors and solutions |

## Format strategies

Choose how audiobooks are downloaded via the `format` setting in `config.yaml`:

| Strategy | Description |
|----------|-------------|
| `m4b_mp3_fallback` *(default)* | Try M4B first; fall back to MP3 if unavailable. Best for most users. |
| `mp3_only` | Download MP3 ZIP parts only. For players that don't support M4B. |
| `m4b_only` | Download M4B only; skip the book if unavailable. For single-file purists. |

## Path customization

Output paths follow a sensible default (`Author/Series/Book N Title` for series, `Author/Title` for standalones) but can be fully customized with tokens like `{FIRST_AUTHOR}`, `{BOOK_TITLE}`, `{SERIES_NAME}`, `{ISBN}`, `{PUBLICATION_YEAR}`, and more. See [Path Patterns](docs/path-patterns.md) for details.

## Comparison

This project is a **lightweight Python alternative** to the [Kotlin-based Docker container](https://github.com/advplyr/librofm-audiobook-downloader) that runs a full JVM. If you want something you can `pip install`, debug with standard Python tooling, and run without Docker — this is it.

## License

GPL-3.0. See [LICENSE.md](LICENSE.md).
