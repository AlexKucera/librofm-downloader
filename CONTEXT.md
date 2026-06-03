# Libro.fm Downloader — Domain Glossary

## Purpose
A Python script that logs into a Libro.fm account and downloads owned audiobooks.
Runs once per invocation (manual or cron). No daemon, no server, no Docker.

## Terms

### **Book**
An audiobook owned by the user's Libro.fm account. Has: title, authors, ISBN,
cover_url, publisher, publication_date, description, genres, series (optional),
series_num (optional), narrators, duration, track_count, pdf_extras.

### **Format**
The audio format to download. Three modes:
- **m4b_mp3_fallback** (default) — Try packaged M4B first; if unavailable, download MP3 ZIP.
- **mp3_only** — Download MP3 ZIP only.
- **m4b_only** — Download M4B only; skip book if unavailable.

### **M4B**
Packaged audiobook file (Apple Audiobook container). Single file, typically
contains embedded cover art. Served directly from Libro.fm's CDN.

### **MP3**
Fallback format. Delivered as a download manifest containing N ZIP parts,
each containing one or more `.mp3` track files. Must be extracted.

### **Download Manifest**
API response (`/api/v10/download-manifest?isbn=`) listing ZIP part URLs and
track metadata (number, chapter_title) for MP3-format books.

### **Path Pattern**
Template string resolving output file paths from book metadata. Tokens:
FIRST_AUTHOR, ALL_AUTHORS, SERIES_NAME, SERIES_NUM, BOOK_TITLE, ISBN,
FIRST_NARRATOR, ALL_NARRATORS, PUBLICATION_YEAR, PUBLICATION_MONTH,
PUBLICATION_DAY.

### **Default Path Behavior**
Not a static pattern — conditional on series data:
- **With series:** <FIRST_AUTHOR>/<SERIES_NAME>/Book <SERIES_NUM> <BOOK_TITLE>
- **Without series:** <FIRST_AUTHOR>/<BOOK_TITLE>

Custom PATH_PATTERN in config overrides this default.

### **Output Structure**
- Book with accompanying files (PDF extras, cover art) → subdirectory:
  `Author/Series/Book 1 Book Title/Book Title.m4b` (+ pdf, cover inside)
- Book without accompanying files → file is leaf node:
  `Author/Series/Book 2 Another Book.m4b` or `Author/Standalone Book.m4b`

### **Accompanying Files**
PDF extras and cover art. Their presence triggers subdirectory creation
for the audiobook file.

### **Sanitization**
Applied to every path component derived from book metadata:
- Replace `:` with ` -`
- Strip `< > / \ | ? *` and control characters (\x00-\x1F)
- Remove trailing dots
- Trim whitespace
- Cap at 255 characters
- Preserve dashes, commas, apostrophes, parentheses

### **Download History**
JSON file mapping ISBN → {title, format, path, downloaded_at}.
Source of truth for "has this been downloaded." Written only after
successful complete download. Delete entry or file to re-download.

### **Partial File**
`.m4b.partial` or `.zip.partial` — in-progress download. Supports resume
via HTTP Range header on next run. Renamed to final filename on completion.

### **Secrets File**
`secrets.yaml` — gitignored, contains credentials. Deep-merged over
`config.yaml` at runtime. Script errors if credentials found in config.yaml.

### **Sync Run**
One execution of the script: auth → fetch library → filter undownloaded
→ download each (sequentially or in parallel) → write history → print summary → exit.

### **Workers**
Number of simultaneous book downloads during a Sync Run. Configured via `workers` in
config.yaml, `--workers N` CLI flag (CLI overrides config), or defaults to 3.
Set to 1 for sequential behavior (identical to pre-parallelism). Libro.fm API calls
are capped at 3 concurrent via semaphore regardless of worker count; CDN downloads
are unbounded.

## API Surface (Libro.fm)

Base URL: https://libro.fm/
Required headers: X-LibroFm-AppVer, User-Agent

Endpoints:
- POST /oauth/token — OAuth2 password grant → access_token
- GET /api/v10/library — Paginated library list (Books[])
- GET /api/v10/audiobooks/{isbn}/packaged_m4b — M4B download URL (404 if unavailable)
- GET /api/v10/download-manifest?isbn= — MP3 download manifest (parts[], tracks[])
- GET /api/v10/explore/audiobook_details/{isbn} — Full book details
- GET /api/v10/library/{isbn}/pdf_extra_url?filename= — PDF extra download URL
