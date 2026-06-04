# Code Context — Issue #26: Book Intake Module Extraction

## Files Retrieved

1. `librofm_downloader/downloader.py` (652 lines) — **The monolith to split.** Contains Book dataclass, all path logic (sanitize, resolve_path, needs_subdirectory, token registry), download functions (M4B, ZIP, accompanying files), and orchestration helpers.
2. `librofm_downloader/__init__.py` (2 lines) — Package init; currently exports **nothing** (no `__all__`, no re-exports).
3. `librofm_downloader/orchestrator.py` (277 lines) — Contains `_raw_to_book()` (lines 57–77), the API-shape→Book intake function that **should** move to a new `book.py`.
4. `librofm_downloader/cli.py` (247 lines) — Imports `Book, download_book` from downloader.
5. `tests/test_downloader.py` (1686 lines) — **Primary test file.** Imports Book, sanitize, resolve_path, needs_subdirectory, _resolve_output_dir, download_m4b, download_zip_part, download_book, download_accompanying_files from downloader.
6. `tests/test_orchestrator.py` (877 lines) — Imports `Book` from downloader. Has `_make_raw_book()` helper (line 19) that builds raw API dicts. Tests `_raw_to_book` indirectly via `download_all_books()`.
7. `tests/test_progress.py` (1286 lines) — Imports `Book` from downloader for progress bar book-identity tests.
8. `tests/test_client.py` (566 lines) — Uses raw API dict keys (`isbn`, `title`, `audiobooks`) in mock responses; imports `download_m4b` from downloader for one integration test.
9. `tests/test_cli.py` (1423 lines) — Does NOT import from downloader directly (imports from cli which re-exports nothing).
10. `librofm_downloader/client.py` (226 lines) — `fetch_library()` returns `list[dict]` raw API dicts under key `"audiobooks"`.

---

## Key Code

### 1. `Book` dataclass (`downloader.py:36–51`)

```python
@dataclass(frozen=True)
class Book:
    """Immutable book metadata record from Libro.fm."""
    title: str
    authors: list[str]
    narrators: list[str]
    isbn: str
    series: str = ""
    series_num: int | None = None
    cover_url: str = ""
    pdf_extras: bool = False
    publication_year: int | None = None
    publication_month: int | None = None
    publication_day: int | None = None
```

**11 fields, frozen/immutable.** This is the central domain object.

### 2. `_raw_to_book()` — API-shape intake (`orchestrator.py:57–77`)

```python
def _raw_to_book(raw: dict) -> Book:
    """Convert a Libro.fm API dict to a Book object."""
    audiobook_info = raw.get("audiobook_info", {}) or {}
    narrators = audiobook_info.get("narrators", []) or raw.get("narrators", [])

    return Book(
        title=raw.get("title", "Unknown"),
        authors=raw.get("authors", []),
        narrators=narrators,
        isbn=raw.get("isbn", "?"),
        series=raw.get("series", ""),
        series_num=raw.get("series_num"),
        cover_url=raw.get("cover_url", ""),
        pdf_extras=bool(audiobook_info.get("pdf_extras")) if audiobook_info else False,
        publication_year=raw.get("publication_year"),
        publication_month=raw.get("publication_month"),
        publication_day=raw.get("publication_day"),
    )
```

**Raw API dict keys consumed:** `title`, `authors`, `narrators`, `isbn`, `series`, `series_num`, `cover_url`, `publication_year`, `publication_month`, `publication_day`, and nested `audiobook_info.narrators`, `audiobook_info.pdf_extras`.

### 3. Path helper functions (all in `downloader.py`)

| Function | Lines | Purpose |
|----------|-------|---------|
| `sanitize(component)` | 53–75 | Filesystem-safe path component sanitization |
| `_ILLEGAL_CHARS` | 30 | Translation table: `<>/\\|?*` |
| `_CONTROL_CHARS` | 33 | Set of U+0000–U+001F |
| `_TOKEN_REGISTRY` | 81–93 | 12 token → (attr, formatter) mappings |
| `_token_value(book, token)` | 96–113 | Resolve single token to string |
| `resolve_path(book, pattern)` | 116–132 | Main entry: custom pattern or default |
| `_resolve_default_path(book)` | 135–148 | Author/Series/Book N Title logic |
| `_resolve_custom_pattern(book, pattern)` | 151–161 | `{TOKEN}` regex substitution |
| `needs_subdirectory(book)` | 164–172 | PDF extras → True |
| `_resolve_output_dir(book, output_base, config)` | 353–379 | Full Path resolution with config |

### 4. Everything else in `downloader.py` (download machinery — stays)

| Symbol | Lines | Purpose |
|--------|-------|---------|
| `InterruptedDownload` | 10–17 | Exception class |
| `CHUNK_SIZE` | 183 | 8 MB constant |
| `_part_filename_from_url(url)` | 186–191 | URL → safe filename |
| `download_zip_part(...)` | 194–272 | ZIP download + extract + resume |
| `download_m4b(...)` | 283–350 | M4B streaming download + resume |
| `download_book(...)` | 382–455 | Format strategy orchestrator |
| `_download_mp3(...)` | 458–490 | MP3 manifest → ZIP parts |
| `_cover_filename_from_url(url)` | 501–505 | Cover URL → filename |
| `_download_cover(...)` | 508–552 | Cover art streaming download |
| `_download_pdf(...)` | 555–585 | PDF extra streaming download |
| `download_accompanying_files(...)` | 588–632 | Cover + PDF dispatch |
| `_write_history(...)` | 635–651 | HistoryEntry writer |

---

## Architecture

### Current module layout

```
librofm_downloader/
├── __init__.py          # (empty — no exports)
├── cli.py               # → imports Book, download_book from downloader
├── client.py            # → fetch_library() returns list[dict] (raw API)
├── config.py            # standalone
├── downloader.py        # ★ MONOLITH: Book + path logic + downloads
├── history.py           # standalone
├── orchestrator.py      # → imports Book from downloader; has _raw_to_book()
└── progress.py          # standalone
```

### Import graph for symbols being extracted

```
Book (downloader.py:36)
  ├── imported by: orchestrator.py:21
  ├── imported by: cli.py:13
  ├── imported by: test_downloader.py:10
  ├── imported by: test_orchestrator.py:11
  └── imported by: test_progress.py:9

_raw_to_book (orchestrator.py:57)
  └── called by: orchestrator.py:143 inside download_all_books()

Path functions (sanitize, resolve_path, needs_subdirectory, _resolve_output_dir)
  └── imported by: test_downloader.py:9-18
```

### Data flow

```
client.fetch_library() → list[dict]  (raw API response)
       ↓
orchestrator._raw_to_book(raw) → Book  (intake/conversion)
       ↓
downloader.resolve_path(Book) → str  (path logic)
downloader.sanitize(str) → str       (component safety)
downloader.needs_subdirectory(Book) → bool  (layout decision)
       ↓
downloader.download_book(Book, ...) → Path  (I/O)
```

### Raw API dict shape (from test patterns)

The Libro.fm API returns books as dicts inside an `"audiobooks"` list:

```python
{
    "isbn": "9781234567890",
    "title": "Book Title",
    "authors": ["Author Name"],
    "narrators": ["Narrator Name"],            # sometimes at top level
    "cover_url": "https://...",
    "series": "Series Name",
    "series_num": 1,
    "publication_year": 2024,
    "publication_month": 6,
    "publication_day": 1,
    "audiobook_info": {                         # nested block
        "narrators": ["Narrator Name"],         # alternate narrator location
        "pdf_extras": True,
    }
}
```

The `_make_raw_book()` helper in `test_orchestrator.py:19–36` is the canonical test fixture builder.

---

## Test Inventory

| File | Lines | Tests | Imports from downloader |
|------|-------|-------|------------------------|
| `test_downloader.py` | 1686 | ~97 tests | Book, sanitize, resolve_path, needs_subdirectory, _resolve_output_dir, download_m4b, download_zip_part, download_book, download_accompanying_files, CHUNK_SIZE, InterruptedDownload |
| `test_orchestrator.py` | 877 | ~20 tests | Book (+ uses _raw_to_book indirectly) |
| `test_progress.py` | 1286 | ~80+ tests | Book, download_m4b, download_zip_part, download_book |
| `test_client.py` | 566 | ~20 tests | download_m4b (1 import) |
| `test_cli.py` | 1423 | ~60 tests | *(none — goes through cli.run)* |
| **Total** | **6837** | **~277** | |

**Total test count: 6,513 lines across 7 files.**

### Test classes in `test_downloader.py` relevant to extraction target:

| Class | Lines | What it tests |
|-------|-------|---------------|
| `TestSanitizeIllegalChars` | 24–45 | `sanitize()` strips chars |
| `TestSanitizeColonReplacement` | 46–58 | `sanitize()` colon → ` -` |
| `TestSanitizeControlChars` | 60–77 | `sanitize()` strips control chars |
| `TestSanitizeTrailingDots` | 79–93 | `sanitize()` trailing dots |
| `TestSanitizeTrimWhitespace` | 95–109 | `sanitize()` whitespace trim |
| `TestSanitizeLengthCap` | 111–125 | `sanitize()` 255 cap |
| `TestSanitizePreservedChars` | 127–147 | `sanitize()` preserves safe chars |
| `TestSanitizeEdgeCases` | 149–166 | `sanitize()` edge cases |
| `TestDefaultPathSeriesWithNumber` | 172–211 | `resolve_path()` series+num |
| `TestDefaultPathSeriesWithoutNumber` | 213–227 | `resolve_path()` series only |
| `TestDefaultPathNoSeries` | 229–243 | `resolve_path()` flat |
| `TestCustomPathPattern` | 245–373 | `resolve_path()` tokens |
| `TestNeedsSubdirectory` | 375–431 | `needs_subdirectory()` |
| `TestOutputStructure` | 1509–1685 | `_resolve_output_dir()` |

**These ~42 test classes (~170+ test methods) are candidates for ownership by `test_book.py` / `test_path.py`.**

---

## Start Here

**Start with `librofm_downloader/downloader.py`** — it's the 652-line monolith containing everything to be extracted. The extraction boundary is clear:

1. **`book.py`** should own: `Book` dataclass + `_raw_to_book()` (moved from orchestrator.py)
2. **`path.py`** should own: `sanitize()`, `resolve_path()`, `_resolve_default_path()`, `_resolve_custom_pattern()`, `_token_value()`, `_TOKEN_REGISTRY`, `_ILLEGAL_CHARS`, `_CONTROL_CHARS`, `needs_subdirectory()`, `_resolve_output_dir()`
3. **`downloader.py`** keeps: All download I/O functions (`download_m4b`, `download_zip_part`, `download_book`, `_download_mp3`, `download_accompanying_files`, helpers, `InterruptedDownload`, `CHUNK_SIZE`)

**Key risk areas:**
- `__init__.py` currently exports nothing — decide whether to add re-exports for backward compat
- 6 files import from `downloader.py`; all will need updated import paths
- `test_downloader.py` is 1686 lines and will need to be split (book/path tests vs. download I/O tests)
- `_resolve_output_dir()` calls both `needs_subdirectory()` and `resolve_path()` — these become intra-module calls in `path.py`
- `download_book()` and friends call `sanitize()`, `resolve_path()`, `needs_subdirectory()` — these become cross-module imports from `path.py`
