# librofm-downloader

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-green.svg)](https://github.com/AlexKucera/librofm-downloader/blob/main/LICENSE.md)

**Download owned audiobooks from your Libro.fm account** — a lightweight, dependency-minimal CLI tool written in Python.

No Docker. No JVM. Just Python and go.

## Features

- **Full library sync** — fetches every audiobook in your Libro.fm account with automatic pagination
- **Interactive book selection** — pick which books to download with `--select` (checkbox prompt)
- **M4B + MP3 formats** — downloads M4B (single file) or MP3 (ZIP parts extracted) with automatic fallback
- **Chapter renaming** — MP3 files renamed with chapter titles from the manifest (configurable)
- **Resume support** — interrupted downloads pick up where they left off via `.partial` files
- **Parallel downloads** — configurable worker count (`--workers N`, default 3) with graceful Ctrl+C drain
- **Cover art & PDF extras** — optional download of cover images and accompanying PDFs
- **Customizable output paths** — token-based patterns for organizing your library on disk
- **TTY-aware progress** — rich progress bars in your terminal, clean log lines in cron jobs
- **Download history** — tracks what's been downloaded so re-runs only fetch new books
- **Graceful failure isolation** — one failed book doesn't stop the rest

## Quick Start

```bash
# 1. Install from source
git clone https://github.com/AlexKucera/librofm-downloader.git
cd librofm-downloader
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e .

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
librofm-downloader
```

See [Quickstart](quickstart.md) for the full walkthrough, or jump to [Configuration Reference](configuration.md) for every option.
