# Path Patterns

How librofm-downloader organizes files on disk, and how to customize the layout with tokens.

## Default behavior

When no custom pattern is set, the output path is determined by **conditional logic** based on whether a book belongs to a series:

### Standalone book (no series)

```
{FIRST_AUTHOR}/{BOOK_TITLE}
```

Example: `Brandon Sanderson/The Way of Kings.m4b`

### Book in a series (with series number)

```
{FIRST_AUTHOR}/{SERIES_NAME}/Book {SERIES_NUM} {BOOK_TITLE}
```

Example: `Brandon Sanderson/Stormlight Archive/Book 1 The Way of Kings.m4b`

### Book in a series (no series number)

```
{FIRST_AUTHOR}/{SERIES_NAME}/{BOOK_TITLE}
```

Example: `J.K. Rowling/Harry Potter/Harry Potter and the Sorcerer's Stone.m4b`

### Subdirectory logic

A book gets its own subdirectory when **any** of these are true:

- The book has **PDF extras** available (`pdf_extras: true`)
- `download_covers: true` **and** the book has a cover URL

Otherwise the audio file sits directly under the author directory as a flat file.

## Available tokens

Use these inside `{TOKEN}` placeholders in a custom pattern:

| Token | Source | Example value | Notes |
|-------|--------|---------------|-------|
| `{FIRST_AUTHOR}` | First item in authors list | `Brandon Sanderson` | Empty if no authors |
| `{ALL_AUTHORS}` | Authors joined by `, ` | `Sanderson, Brandon` | Empty if no authors |
| `{SERIES_NAME}` | Series name | `Stormlight Archive` | Empty string if not in a series |
| `{SERIES_NUM}` | Series position integer | `1` | Empty if not in a series or no number |
| `{BOOK_TITLE}` | Book title | `The Way of Kings` | Sanitized for filesystem safety |
| `{ISBN}` | ISBN identifier | `9780743565400` | As returned by the API |
| `{FIRST_NARRATOR}` | First narrator | `Kate Reading` | Empty if no narrators |
| `{ALL_NARRATORS}` | Narrators joined by `, ` | `Kate Reading, Michael Kramer` | Empty if no narrators |
| `{PUBLICATION_YEAR}` | Year published | `2024` | Empty if unknown |
| `{PUBLICATION_MONTH}` | Month published | `8` | Empty if unknown |
| `{PUBLICATION_DAY}` | Day published | `15` | Empty if unknown |

## Custom patterns

To override the default conditional logic, set a `path_pattern` key in your config:

```yaml
librofm:
  format: m4b_mp3_fallback
  output_dir: ./audiobooks
  path_pattern: "{PUBLICATION_YEAR}/{FIRST_AUTHOR} - {BOOK_TITLE}"
```

This would produce paths like:

```
./audiobooks/2024/Brandon Sanderson - The Way of Kings.m4b
./audiobooks/2023/Suzanne Collins - The Hunger Games.m4b
```

> [!NOTE]
> Custom patterns are applied via regex substitution (`{TOKEN_NAME}` → value).
> Unknown tokens resolve to empty strings — no error is raised.
> Each path component is sanitized (colons replaced, illegal chars stripped, capped at 255 chars).

## Pattern examples

### Flat by author

```yaml
path_pattern: "{ALL_AUTHORS}/{BOOK_TITLE}"
```

Output:
```
audiobooks/Sanderson, Brandon/The Way of Kings.m4b
audiobooks/Collins, Suzanne/The Hunger Games.m4b
```

### Organized by series

```yaml
path_pattern: "{FIRST_AUTHOR}/{SERIES_NAME}/{SERIES_NUM:03d} - {BOOK_TITLE}"
```

Output:
```
audiobooks/Brandon Sanderson/Stormlight Archive/001 - The Way of Kings.m4b
audiobooks/Brandon Sanderson/Mistborn/001 - The Final Empire.m4b
```

> [!WARNING]
> Python format specs like `:03d` are **not supported** — tokens produce plain strings only.
> Use `{SERIES_NUM}` directly; it will render as `1`, `2`, etc.

### By narrator

```yaml
path_pattern: "{FIRST_NARRATOR}/{BOOK_TITLE}"
```

Output:
```
audiobooks/Kate Reading/The Way of Kings.m4b
```

### ISO-style date prefix

```yaml
path_pattern: "{PUBLICATION_YEAR}-{PUBLICATION_MONTH}-{PUBLICATION_DAY}/{FIRST_AUTHOR}/{BOOK_TITLE}"
```

Output:
```
audiobooks/2024-8-15/Brandon Sanderson/The Way of Kings.m4b
```

## Path sanitization

Every path component goes through sanitization before being written to disk:

1. **Colons** (`:`) → replaced with ` -`
2. **Illegal characters** `< > / \ | ? *` → stripped
3. **Control characters** (U+0000–U+001F) → stripped
4. **Trailing dots** → removed
5. **Whitespace** → trimmed
6. **Length** → capped at 255 characters

Preserved characters include dashes, commas, apostrophes, parentheses, and non-trailing periods.
