# Changelog

All notable changes to this project will be documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2026-05-01

### Changed

- Refined **deduplication modes** in `core.py` to better match their names and provide more useful behavior for YouTube transcripts:
  - `consecutive`:
    - Now strictly removes only **exact consecutive duplicate cues** (identical `text` appearing immediately after each other).
    - This is a conservative mode that avoids altering rolling captions unless they contain literal back-to-back duplicates.
  - `consecutive-overlap`:
    - Now performs **word-level overlap removal only between adjacent cues**.
    - Designed for rolling/auto captions where each cue partially repeats the previous one.
    - Compares each cue only against the **immediately previous kept cue**, trimming the overlapping part and keeping only the new portion.
  - `global`:
    - Now performs **word-level overlap removal against all accumulated text so far**.
    - This is the most aggressive mode: once text has appeared in the transcript, any later cue that only repeats it is skipped or trimmed so that only genuinely new text remains.
- Updated README documentation for deduplication modes to describe:
  - The new behavior of `consecutive`, `consecutive-overlap`, and `global`.
  - Practical caveats and recommended usage (e.g. `consecutive-overlap` for auto-generated captions, `global` for maximally compressed transcripts).

### Notes

- These changes affect how deduplication behaves compared to version `0.2.0`, but there were no external users at the time of the change.
- CLI and GUI still expose the same `--dedupe` options (`consecutive`, `consecutive-overlap`, `global`, `none`); only their internal behavior has been refined.


## [0.2.0] - 2026-05-01

### Added

- New **chapter mode system** replacing the old boolean chapter split:
  - `chapter_mode="none"` – single transcript file, no explicit chapter headings.
  - `chapter_mode="inline"` – single transcript file, with chapter headings/sections inline.
  - `chapter_mode="files"` – one file per chapter in a `{base}.chapters/` directory.
- CLI support for chapter modes:
  - `--chapter-split` → `chapter_mode="files"`.
  - New `--chapter-inline` → `chapter_mode="inline"`.
  - `--no-chapter-split` → `chapter_mode="none"`.
- GUI support for chapter modes:
  - Replaces the old “Split by Chapters” checkbox with a `Chapter Mode` combobox (`none`, `inline`, `files`).
- New **OLED theme** in the GUI:
  - True-black backgrounds optimized for OLED displays.
  - Keeps all text and controls readable while maximizing dark areas.
- Stronger **dark-mode styling** for the GUI:
  - Dark/OLED theme now also styles dropdown lists, scrollbars, and log output area.
  - Fixes white-on-white text issues in combobox dropdowns.
- New Qt-based GUI:
  - The GUI is now implemented with **PySide6 (Qt)** instead of Tkinter.
  - Uses Qt’s `QThread` + signals/slots for background processing and safe logging back to the UI.
  - Uses Qt Style Sheets for consistent theming.

### Changed

- **GUI toolkit**:
  - Replaced the Tkinter GUI with a PySide6 (Qt) GUI in `gui.py`.
  - The external API for running the GUI remains `run_gui()`, so CLI and core code are unchanged.
- **Core output rendering**:
  - `render_output` and its helpers now accept a `chapter_mode` parameter and, for applicable formats, render inline chapter headings when `chapter_mode="inline"`.
  - TXT and Markdown output:
    - `chapter_mode="none"`: single transcript (optionally per-chapter files when the caller passes a `chapter_title`).
    - `chapter_mode="inline"`: single file, with chapter headings inserted inline when chapters are available.
  - JSON and CSV output retain a single-file structure but now include `chapter_mode` in JSON metadata.
- **`write_outputs`** behavior:
  - Now switches based on `chapter_mode`:
    - `"none"` → single file, no explicit chapter sections.
    - `"inline"` → single file with inline chapter headings (where supported by the format).
    - `"files"` → per-chapter files in a `{base}.chapters` directory.
- **CLI prompting logic**:
  - Interactive prompts now ask whether to “Split transcript by chapters” and map the answer to `chapter_mode="files"` or `"none"` when `--chapter-mode` flags aren’t explicitly set.
- **Configuration persistence**:
  - Config file schema extended to include:
    - `"theme"`: `"light"`, `"dark"`, or `"oled"`.
    - `"chapter_mode"`: `"none"`, `"inline"`, or `"files"`.
  - Existing configs that used `"dark_mode"` (bool) and `"chapter_split"` (bool) are migrated:
    - `dark_mode=True` → `theme="dark"`.
    - `chapter_split=True` → `chapter_mode="files"`.
- **Windows title bar theming** (Qt GUI):
  - The new Qt-based GUI attempts to align the title bar with the selected theme on Windows 11 using a combination of:
    - `Qt.ColorScheme` (Light/Dark hint),
    - `DwmSetWindowAttribute` calls to control immersive dark mode and title bar colors.
  - Behavior still ultimately depends on the OS and theme settings, but it is now handled by Qt instead of raw Tk.

### Fixed

- GUI combobox dropdowns in dark mode:
  - Dropdown lists were previously white with light text in the Tkinter GUI, making them unreadable.
  - The Qt GUI uses Qt Style Sheets to ensure dropdown backgrounds and text colors match the selected theme.
- Light-mode UI in the GUI:
  - Light mode now uses explicit color values rather than invalid empty color strings and renders correctly.
- More robust handling of invalid/legacy configuration:
  - Invalid `theme`, `format`, `dedupe`, or `chapter_mode` values in the config file are now normalized to safe defaults.

### Breaking Changes

- The desktop GUI now depends on **PySide6** instead of Tkinter:
  - You must install `PySide6` (see README for installation details).
  - The CLI and core API remain backward compatible.
- The old boolean `chapter_split` flag in the core has been replaced with a `chapter_mode` string:
  - Any direct programmatic use of `ProcessOptions` must now provide a `chapter_mode` value (`"none"`, `"inline"`, or `"files"`).

---

## [0.1.0] - 2026-05-01

- Initial release:
  - Tkinter-based desktop GUI.
  - CLI interface for downloading and cleaning YouTube subtitles with `yt-dlp`.
  - Multiple output formats: TXT, Markdown, JSON, CSV.
  - Deduplication modes: `consecutive`, `consecutive-overlap`, `global`, `none`.
  - Basic chapter-aware splitting into per-chapter files (boolean `chapter_split`).
  - Optional timestamps, language priority, auto/manual caption selection.
  - Configurable options persisted in a JSON config file.
