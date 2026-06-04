# ADR 0006: Select Mode — Interactive Book Selection

## Status

Accepted (2026-06-03)

## Context

Libro.fm-downloader downloads **all** undownloaded books from the user's library on every run. The only controls are `--limit N` (cap count) and download-history filtering (skip already-downloaded). Users with large libraries (50+ books) or limited storage want to choose specific books rather than downloading everything.

The tool already supports two output modes: TTY (Rich progress bars) and non-TTY/cron (plain log lines). Any interactive feature must respect this duality.

## Decision

Add a `--select` CLI flag (off by default, CLI-only — no config.yaml option) that opens an interactive checkbox TUI before downloading. When active, select mode supersedes both the history filter and `--limit`.

### Library: questionary

| Library | Verdict |
|---|---|
| **questionary** | **Chosen** — mature, Rich-compatible styling, checkbox prompt with fuzzy search, most popular Python interactive CLI library |
| inquirer | Rejected — lighter but fewer features, less active maintenance |
| Custom Rich-based | Rejected — more code to write/maintain, Rich's Live is powerful but not designed for form-style interaction |

### Non-TTY behavior

**Hard exit with error.** Select mode requires interactivity by definition. If stdout is not a terminal (piped, cron, redirected), print `"--select requires an interactive terminal (TTY)"` and exit 1.

Rationale: silent degradation would be surprising (user expects to pick books, gets all-or-nothing instead). A fallback to numbered-list input was considered but adds a second codepath to test and a degraded experience that most users won't encounter.

### Row format

`[ ] N. Title — First Author [Series #]`

- Number for easy reference
- Title + first author (full author list available elsewhere if needed)
- Series + number when present (helps with series ordering decisions)
- Duration deliberately omitted: not available from `/api/v10/library` endpoint; fetching per-book from `/api/v10/explore/audiobook_details/{isbn}` adds N API calls and latency before the UI renders

### Default selection state

**All unchecked.** User must actively opt-in each book. Prevents accidental bulk downloads of large libraries.

### Already-downloaded books

**Hidden completely.** The selection list shows only undownloaded books. Already-downloaded books are filtered out before the TUI opens, same as today's automatic pipeline stage. If all books are downloaded, print the existing `"All caught up! No new books to download."` message and exit 0 — identical to non-select behavior.

### Post-selection confirmation

Always show a y/N summary after selection:

```
3 books selected for download:
 • The Great Gatsby — F. Scott Fitzgerald
 • Dune — Frank Herbert
 • Project Hail Mary — Andy Weir

Proceed? [y/N] 
```

Prevents fat-finger mistakes on large libraries. No configurable threshold — always confirm.

### Empty selection

If user presses Enter without checking any boxes: print `"No books selected. Exiting."` and exit 0. Not an error — choosing nothing is valid.

### Pipeline integration

```
BEFORE:  auth → fetch_library → filter_downloaded → [limit] → download_all
AFTER:   auth → fetch_library → [--select? → select_books() : filter_downloaded+limit] → download_all
```

When `--select` is on:
1. Fetch full library
2. Remove already-downloaded books (same `DownloadHistory` check)
3. Verify TTY availability → error if not
4. Convert raw dicts to `Book` objects
5. Open questionary checkbox prompt
6. On confirm: show summary, ask y/N
7. Pass selected books to existing `download_all_books()` orchestrator
8. Continue with normal progress reporting, history writing, summary

### Code location

New module: `librofm_downloader/selector.py`

Single public function:
```python
def select_books(books: list[Book]) -> list[Book]:
    """Open interactive TUI, return user-selected books."""
```

CLI integration in `cli.py`: add `--select` argument, branch between select mode and existing auto-filter path before the download stage.

## Consequences

### Positive

- Users control exactly what downloads — no more bulk downloads of unwanted books
- Works naturally with existing parallel download infrastructure (`download_all_books` accepts any book list)
- Zero changes to download pipeline, history, or progress reporting
- Clear mental model: `--select` means "I'll pick"; no flag means "auto-download everything new"

### Negative

- New runtime dependency: `questionary` (adds ~200KB installed, pulls in `prompt_toolkit`)
- Interactive-only feature: cannot be used in cron or piped contexts
- `--limit` becomes meaningless when `--select` is on (documented, not silently ignored)
- Test complexity: questionary's TUI requires mocking/patching for unit tests

### Risks

- **questionary abandonment**: mitigated by it being the most popular choice; thin wrapper around `prompt_toolkit`; could swap to custom Rich implementation if needed
- **Large libraries (100+ books)**: questionary's checkbox handles scrolling natively; row format is compact; fuzzy search helps narrow down
- **Terminal width**: rows are ~60-80 chars average; should fit 80-column terminals

## Alternatives Considered

1. **Numbered list + comma input**: Zero dependencies, works anywhere. Rejected — poor UX for 20+ books, no visual feedback, hard to correct mistakes.
2. **Per-book y/n prompts**: Simplest possible interactive mode. Rejected — unbearable for 30+ books ("Download this? [y/n]" × 30).
3. **Config-driven include/exclude lists**: `only_isbns: [...]` or `skip_titles: [...]` in config.yaml. Rejected — requires editing config before each run; defeats the purpose of "pick what I want right now."
4. **Web UI / separate selector tool**: Overengineered for a CLI-first tool.
