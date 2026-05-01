# yt-transcript-cleaner

A Python desktop and command-line application for downloading and cleaning YouTube subtitles into readable transcript files.

It uses `yt-dlp` to download subtitles from YouTube videos and converts them to TXT, Markdown, JSON, or CSV. It supports manual captions, auto-generated captions, language priority, optional timestamps, chapter-aware splitting or inline chapter headings, batch processing, configurable deduplication, dark and OLED themes, settings that persist between sessions, and desktop GUI and CLI interfaces.

The desktop GUI is implemented using **PySide6 (Qt)**, and the core logic is shared with the CLI.

## Features

- Multiple output formats: TXT, Markdown, JSON, CSV
- Subtitle cleaning: removes VTT markup and normalizes whitespace
- Deduplication modes:
  - `consecutive`: removes exact duplicate cues that appear directly after each other
  - `consecutive-overlap`: removes rolling-caption overlap from adjacent cues, useful for YouTube auto-generated captions
  - `global`: removes repeated cue text across the whole transcript
  - `none`: no deduplication
- Optional timestamps
- Chapter-aware handling:
  - `none`: single transcript file with no explicit chapter headings
  - `inline`: single transcript file with chapter headings/sections inserted inline
  - `files`: optionally split output into separate per-chapter files when video chapters are available
- Batch processing from a URL list file
- Language priority for subtitle selection
- Manual and auto-generated captions
- Desktop GUI using **PySide6 (Qt)**
- Dark and OLED theme support (with best-effort Windows dark title bar integration)
- Configurable options that persist between sessions
- Command-line interface for automated workflows
- Cross-platform support for Windows, macOS, and Linux

## Deduplication modes explained

YouTube subtitles can contain repeated text in different ways. This tool provides several deduplication modes to handle different cases.

### `consecutive`

Removes exact duplicate caption cues when they appear directly after each other.

Input:

```text
Hello!
Hello!
Goodbye!
```

Output:

```text
Hello!
Goodbye!
```

This is useful when the subtitle file contains identical repeated cues.

### `consecutive-overlap`

Removes overlapping text from adjacent cues. This is especially useful for YouTube auto-generated subtitles, which often use rolling captions.

Input:

```text
Hello there. Master Hellish here, and
Hello there. Master Hellish here, and welcome to a very special trip down
welcome to a very special trip down memory lane.
```

Output:

```text
Hello there. Master Hellish here, and welcome to a very special trip down memory lane.
```

This is the recommended mode when auto-generated captions produce repeated phrases in the final transcript.

### `global`

Removes repeated cue text across the whole transcript, not just adjacent cues.

Input:

```text
Welcome back.
Today we are looking at trains.
Welcome back.
Let's begin.
```

Output:

```text
Welcome back.
Today we are looking at trains.
Let's begin.
```

Use this carefully, since repeated phrases can be intentional in spoken content.

### `none`

Disables deduplication.

## Installation

### Prerequisites

- Python 3.10 or newer
- `yt-dlp`
- `PySide6` (for the GUI)

### Install from source

Clone the repository:

```bash
git clone https://github.com/YOUR-USERNAME/yt-transcript-cleaner.git
cd yt-transcript-cleaner
```

Create and activate a virtual environment:

```bash
python -m venv .venv
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

On macOS or Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

The main external dependencies are:

- `yt-dlp` – for downloading subtitles
- `PySide6` – for the Qt-based desktop GUI

## Usage

### GUI mode

Run the application without arguments:

```bash
python -m yt_transcript_cleaner
```

This opens the graphical interface where you can enter a YouTube URL or video ID, choose an output directory, select output options, and start processing.

GUI settings are saved between sessions in a JSON config file, so options such as output format, timestamp preference, deduplication mode, theme (light/dark/OLED), chapter mode, and other choices can be reused the next time you open the app.

On Windows 11, the GUI attempts to align the title bar with the selected theme using Qt and system APIs; the exact appearance may still depend on your OS theme and personalization settings.

### CLI mode

Run with the CLI interface:

```bash
python -m yt_transcript_cleaner --cli [OPTIONS]
```

### Basic examples

Download and clean subtitles from a single video:

```bash
python -m yt_transcript_cleaner --cli --url "https://www.youtube.com/watch?v=VIDEO_ID"
```

Specify output format and output directory:

```bash
python -m yt_transcript_cleaner --cli \
  --url "https://www.youtube.com/watch?v=VIDEO_ID" \
  --format json \
  --outdir ./transcripts
```

Use overlap-aware deduplication for auto-generated captions:

```bash
python -m yt_transcript_cleaner --cli \
  --url "VIDEO_ID" \
  --dedupe consecutive-overlap
```

Include timestamps and split output into per-chapter files (when chapters are available):

```bash
python -m yt_transcript_cleaner --cli \
  --url "VIDEO_ID" \
  --with-timestamps \
  --chapter-split
```

Keep a single file but insert chapter headings inline:

```bash
python -m yt_transcript_cleaner --cli \
  --url "VIDEO_ID" \
  --with-timestamps \
  --chapter-inline
```

Batch process multiple videos from a file:

```bash
python -m yt_transcript_cleaner --cli \
  --url-file videos.txt \
  --format md \
  --outdir ./transcripts
```

For batch mode (`--url-file`), filenames are based on the video titles. The `--output-name` option is only supported for single-video runs (`--url`).

List available subtitles:

```bash
python -m yt_transcript_cleaner --cli \
  --url "VIDEO_ID" \
  --list-subs
```

## CLI options

```text
-u, --url              YouTube video URL or 11-character video ID
--url-file             Batch mode: file containing URLs, one per line
-l, --langs            Language priority, comma-separated
                       Default: en-orig,en,en-US,en-GB
-o, --outdir           Output directory, default: current directory
--output-name          Custom output filename, single video only
--format {txt,md,json,csv}
                       Output format
--with-timestamps      Include timing information
--no-timestamps        Exclude timing information
--chapter-split        Split output into per-chapter files when video chapters are available
--chapter-inline       Keep a single file but insert chapter sections/headings
--no-chapter-split     Keep a single transcript file (no per-chapter splitting)
--no-auto              Do not use auto-generated captions
--dedupe {consecutive,consecutive-overlap,global,none}
                       Duplicate removal mode, default: consecutive
--no-merge             Do not merge captions into paragraphs
--keep-vtt             Keep downloaded VTT files
--list-subs            List available subtitles and exit
--summary-template     Generate summary prompt template
--cookies-from-browser Use browser cookies, for example firefox or chrome
--quiet                Suppress output except errors
--verbose              Show detailed progress information
```

## Output formats

### TXT

Plain text with optional timestamps:

```text
[00:00:05] Welcome to this video about Python programming.

[00:00:12] Today we'll cover the basics and get you started.

[00:01:30] Let's start with variables and data types.
```

When `chapter_mode="inline"` (or `--chapter-inline`), chapter headings (when available) are inserted inline:

```text
=== Introduction ===

[00:00:05] Welcome to this video about Python programming.

=== Basics ===

[00:01:30] Let's start with variables and data types.
```

### Markdown

Markdown output with a title heading and optional timestamps.

Example single-file (no chapter split):

```markdown
# Python Programming Basics

`00:00:05` Welcome to this video about Python programming.

`00:00:12` Today we'll cover the basics and get you started.
```

When using per-chapter files (`--chapter-split` / `chapter_mode="files"`), each per-chapter file contains the video title as `#` and the chapter title as `##`:

```markdown
# Python Programming Basics

## Introduction

`00:00:05` Welcome to this video about Python programming.

`00:00:12` Today we'll cover the basics and get you started.
```

When using inline chapters (`--chapter-inline` / `chapter_mode="inline"`), all chapters are combined into one file with `##` headings within it.

### JSON

Structured output with metadata and transcript blocks:

```json
{
  "video_id": "abc123",
  "title": "Python Programming Basics",
  "url": "https://www.youtube.com/watch?v=abc123",
  "chapter": null,
  "chapter_mode": "inline",
  "generated_at": "2024-01-15T10:30:00.123456+00:00",
  "blocks": [
    {
      "text": "Welcome to this video about Python programming.",
      "chapter": "Introduction",
      "start": "00:00:05",
      "end": "00:00:12",
      "start_seconds": 5.0,
      "end_seconds": 12.0
    }
  ]
}
```

For per-chapter JSON files (`chapter_mode="files"`), each file includes the top-level `"chapter"` name for that file.

### CSV

Tabular output suitable for spreadsheets or data analysis:

```csv
start,end,start_seconds,end_seconds,chapter,text
00:00:05,00:00:12,5.000,12.000,Introduction,Welcome to this video about Python programming.
```

The `chapter` column indicates which chapter each row belongs to (if chapters are available).

## Caption selection

### Manual and auto-generated captions

Manual captions are usually more accurate because they are uploaded by the video creator or community.

Auto-generated captions are produced by YouTube speech recognition and may contain recognition errors, repeated phrases, or rolling-caption overlap.

By default, the tool tries manual captions first, then falls back to auto-generated captions. Use `--no-auto` to disable auto-caption fallback.

For auto-generated captions, `--dedupe consecutive-overlap` is usually the best deduplication mode.

### Language priority

Specify language priority using standard language codes:

```bash
python -m yt_transcript_cleaner --cli --url "VIDEO_ID" --langs en,es,fr
```

Common examples:

```text
en       English
en-US    English, United States
en-GB    English, United Kingdom
es       Spanish
fr       French
de       German
ja       Japanese
ko       Korean
```

The default language priority is:

```text
en-orig,en,en-US,en-GB
```

## Browser cookies

Some videos require authentication, age verification, or region-specific access. Use `--cookies-from-browser` to let `yt-dlp` read cookies from a supported browser:

```bash
python -m yt_transcript_cleaner --cli \
  --url "VIDEO_ID" \
  --cookies-from-browser chrome
```

Supported browsers depend on `yt-dlp`, but commonly include:

```text
chrome, chromium, brave, edge, firefox, opera, safari
```

## Chapter-based handling

When chapters are available, you can choose how they are represented in the output:

- `--no-chapter-split` / `chapter_mode="none"`:
  - Single transcript file, no explicit chapter headings.
- `--chapter-inline` / `chapter_mode="inline"`:
  - Single transcript file with chapter headings inserted inline.
- `--chapter-split` / `chapter_mode="files"`:
  - One file per chapter in a `{base}.chapters/` directory, where `{base}` is derived from the video title or `--output-name`.

For example, Markdown per-chapter output might produce:

```text
My Video Title.chapters/
  001-Introduction.md
  002-Main topic.md
  003-Summary.md
```

Inside each per-chapter Markdown file, the structure looks like:

```markdown
# My Video Title

## Introduction

`00:00:00` Welcome to the video.

`00:00:30` In this part, we talk about the basics.
```

If no chapters are available, the tool writes a single transcript file instead of per-chapter files.

## Troubleshooting

### `yt-dlp` not found

Update or install `yt-dlp`:

```bash
python -m pip install -U yt-dlp
```

### No subtitles found

Try the following:

- Check available subtitles with `--list-subs`
- Try another language with `--langs`
- Allow auto-generated captions by not using `--no-auto`
- Use browser cookies with `--cookies-from-browser`

### Video not accessible

If the video is private, age-restricted, region-locked, or otherwise restricted, try browser cookies:

```bash
python -m yt_transcript_cleaner --cli \
  --url "VIDEO_ID" \
  --cookies-from-browser firefox
```

### Repeated text remains in output

If auto-generated captions produce repeated text, use overlap-aware deduplication:

```bash
python -m yt_transcript_cleaner --cli \
  --url "VIDEO_ID" \
  --dedupe consecutive-overlap
```

You can also try listing available subtitles with `--list-subs` and choosing manual captions if they are available.

### Encoding issues

Output files are written using UTF-8. If characters display incorrectly, make sure your terminal, editor, or spreadsheet application opens the file as UTF-8.

## Windows PowerShell examples

```powershell
cd yt-transcript-cleaner

python -m pip install -r requirements.txt

python -m yt_transcript_cleaner

python -m yt_transcript_cleaner --cli --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --format txt --outdir ".\transcripts"

python -m yt_transcript_cleaner --cli --url "VIDEO_ID" --dedupe consecutive-overlap --format md

python -m yt_transcript_cleaner --cli --url-file ".\videos.txt" --format json --with-timestamps

python -m yt_transcript_cleaner --cli --url "VIDEO_ID" --list-subs
```

## Project structure

```text
yt-transcript-cleaner/
├── README.md
├── CHANGELOG.md
├── LICENSE
├── requirements.txt
├── .gitignore
└── yt_transcript_cleaner/
    ├── __init__.py
    ├── __main__.py
    ├── core.py
    ├── cli.py
    └── gui.py
```

## Development

The application is split into a reusable core module and two interfaces.

`core.py` contains the business logic for finding `yt-dlp`, downloading subtitles, parsing VTT files, cleaning text, deduplicating cues, rendering output formats, and writing files.

`cli.py` provides the command-line interface.

`gui.py` provides the PySide6 (Qt) desktop interface and uses background threading (Qt’s `QThread`) so processing does not block the GUI.

Settings are persisted between sessions in a JSON config file.

Both interfaces call the same core functions.

## License

This project is licensed under the MIT License.

This tool depends on `yt-dlp`, which is released under the Unlicense.

## Contributing

Contributions are welcome. Please keep the core logic independent from the GUI and CLI layers so both interfaces continue to behave consistently.