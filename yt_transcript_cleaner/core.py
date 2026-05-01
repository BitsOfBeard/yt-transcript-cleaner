#!/usr/bin/env python3
"""Core module for YouTube subtitle cleaning.

This module contains the reusable logic for downloading and cleaning YouTube
subtitles using yt-dlp. It can be used by both CLI and GUI implementations.
"""

import csv
import html
import io
import json
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

DEFAULT_LANG_PRIORITY = ["en-orig", "en", "en-US", "en-GB"]
OUTPUT_FORMATS = ["txt", "md", "json", "csv"]
YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
TIMING_RE = re.compile(
    r"(?P<start>(?:\d{2}:)?\d{2}:\d{2}\.\d{3})\s+-->\s+"
    r"(?P<end>(?:\d{2}:)?\d{2}:\d{2}\.\d{3})"
)


class AppError(RuntimeError):
    """Exception class for application-specific errors."""
    pass


@dataclass
class Cue:
    """Represents a single subtitle cue with timing and text."""
    start: float
    end: float
    text: str


@dataclass
class Block:
    """Represents a cleaned text block that may span multiple cues."""
    start: float
    end: float
    text: str
    chapter_title: Optional[str] = None


@dataclass
class VideoInfo:
    """Contains metadata about a YouTube video."""
    video_id: str
    title: str
    webpage_url: str
    chapters: List[dict]


@dataclass
class ProcessOptions:
    """Options for processing YouTube subtitles."""
    langs: List[str]
    outdir: Path
    output_name: Optional[str]
    fmt: str
    with_timestamps: bool
    chapter_split: bool
    no_auto: bool
    dedupe: str
    no_merge: bool
    keep_vtt: bool
    list_subs: bool
    summary_template: bool
    cookies_from_browser: Optional[str]
    quiet: bool
    verbose: bool


def normalize_url_or_id(value: str) -> str:
    """Convert a YouTube video ID to a full URL if needed."""
    value = value.strip()
    if YOUTUBE_ID_RE.fullmatch(value):
        return f"https://www.youtube.com/watch?v={value}"
    return value


def sanitize_filename(value: str, fallback: str = "output", max_len: int = 120) -> str:
    """Sanitize a filename by removing invalid characters."""
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    if not value:
        value = fallback
    return value[:max_len].rstrip(" .")


def find_ytdlp_command() -> List[str]:
    """Find the yt-dlp command, first as a Python module, then on PATH."""
    module_check = subprocess.run(
        [sys.executable, "-m", "yt_dlp", "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if module_check.returncode == 0:
        return [sys.executable, "-m", "yt_dlp"]

    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]

    raise AppError(
        "yt-dlp was not found. Install it with:\n"
        f"{sys.executable} -m pip install -U yt-dlp"
    )


def build_ytdlp_args(options: ProcessOptions, skip_download: bool = True) -> List[str]:
    """Build common yt-dlp command arguments."""
    args = []
    if skip_download:
        args.append("--skip-download")
    args.append("--no-playlist")
    if options.cookies_from_browser:
        args += ["--cookies-from-browser", options.cookies_from_browser]
    return args


def run_cmd(
    cmd: List[str],
    cwd: Optional[Path] = None,
    verbose: bool = False,
) -> subprocess.CompletedProcess:
    """Run a subprocess command with proper error handling."""
    if verbose:
        print("Running:", " ".join(cmd), file=sys.stderr)

    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        raise AppError(
            f"Command failed with exit code {result.returncode}:\n"
            f"{' '.join(cmd)}\n\n"
            f"STDOUT:\n{result.stdout}\n\n"
            f"STDERR:\n{result.stderr}"
        )

    return result


def get_video_info(
    ytdlp: List[str],
    url: str,
    options: ProcessOptions,
) -> VideoInfo:
    """Get video metadata from YouTube."""
    proc = run_cmd(
        ytdlp + ["--dump-single-json"] + build_ytdlp_args(options) + [url],
        verbose=options.verbose,
    )

    data = json.loads(proc.stdout)

    video_id = data.get("id") or ""
    if not video_id:
        raise AppError("Could not determine video ID.")

    return VideoInfo(
        video_id=video_id,
        title=data.get("title") or video_id,
        webpage_url=data.get("webpage_url") or url,
        chapters=data.get("chapters") or [],
    )


def list_subtitles(
    ytdlp: List[str],
    url: str,
    options: ProcessOptions,
    log_callback: Optional[Callable[[str], None]] = None,
) -> None:
    """List available subtitles for a video."""
    proc = run_cmd(
        ytdlp + ["--list-subs"] + build_ytdlp_args(options) + [url],
        verbose=options.verbose,
    )

    if proc.stdout:
        output = proc.stdout
        if log_callback:
            log_callback(output)
        else:
            print(output, end="")
    if proc.stderr:
        output = proc.stderr
        if log_callback:
            log_callback(output)
        else:
            print(output, end="", file=sys.stderr)


def snapshot_vtts(directory: Path) -> Set[Path]:
    """Get a snapshot of all VTT files in a directory."""
    return set(directory.glob("*.vtt"))


def pick_best_vtt(
    files: Iterable[Path],
    video_id: str,
    langs: List[str],
) -> Optional[Path]:
    """Pick the best VTT file based on language priority."""
    files = list(files)

    for lang in langs:
        expected = f"{video_id}.{lang}.vtt"
        for file in files:
            if file.name == expected:
                return file

    prefixed = sorted(
        file for file in files
        if file.name.startswith(f"{video_id}.") and file.suffix.lower() == ".vtt"
    )
    if prefixed:
        return prefixed[0]

    return sorted(files)[0] if files else None


def download_subtitles_once(
    ytdlp: List[str],
    url: str,
    workdir: Path,
    info: VideoInfo,
    langs: List[str],
    auto: bool,
    options: ProcessOptions,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Optional[Path]:
    """Download subtitles once, either manual or auto."""
    before = snapshot_vtts(workdir)

    cmd = ytdlp + [
        "--skip-download",
        "--no-playlist",
        "--sub-langs",
        ",".join(langs),
        "--convert-subs",
        "vtt",
        "--force-overwrites",
        "-o",
        "%(id)s.%(ext)s",
    ]

    if options.cookies_from_browser:
        cmd += ["--cookies-from-browser", options.cookies_from_browser]

    if auto:
        cmd.append("--write-auto-subs")
    else:
        cmd.append("--write-subs")

    cmd.append(url)

    run_cmd(cmd, cwd=workdir, verbose=options.verbose)

    after = snapshot_vtts(workdir)
    new_or_changed = after - before

    if not new_or_changed:
        new_or_changed = {
            file for file in after
            if file.name.startswith(f"{info.video_id}.")
        }

    return pick_best_vtt(new_or_changed, info.video_id, langs)


def download_subtitles(
    ytdlp: List[str],
    url: str,
    outdir: Path,
    info: VideoInfo,
    langs: List[str],
    options: ProcessOptions,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[Path, str]:
    """Download subtitles, trying manual then auto if needed."""
    outdir.mkdir(parents=True, exist_ok=True)
    workdir = outdir / f"{info.video_id}.subs"
    workdir.mkdir(parents=True, exist_ok=True)

    manual = download_subtitles_once(
        ytdlp=ytdlp,
        url=url,
        workdir=workdir,
        info=info,
        langs=langs,
        auto=False,
        options=options,
        log_callback=log_callback,
    )
    if manual:
        return manual, "manual"

    if not options.no_auto:
        auto = download_subtitles_once(
            ytdlp=ytdlp,
            url=url,
            workdir=workdir,
            info=info,
            langs=langs,
            auto=True,
            options=options,
            log_callback=log_callback,
        )
        if auto:
            return auto, "auto"

    raise AppError(
        "No matching subtitles found. Try another language, "
        "or allow auto captions by disabling 'no_auto' option."
    )


def parse_timestamp(value: str) -> float:
    """Parse a timestamp string into seconds."""
    parts = value.split(":")
    if len(parts) == 2:
        hours = 0
        minutes = int(parts[0])
        seconds = float(parts[1])
    elif len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
    else:
        raise ValueError(f"Invalid timestamp: {value}")

    return hours * 3600 + minutes * 60 + seconds

def find_overlap(accumulated_text: str, new_text: str) -> Optional[str]:
    """Find word-level overlap between accumulated text and new text.
    
    Searches for the longest sequence of words in new_text that appears
    at the end of accumulated_text, and returns the non-overlapping part.
    
    Args:
        accumulated_text: The text accumulated so far.
        new_text: The new text to check for overlap.
    
    Returns:
        The portion of new_text that doesn't overlap, or None if new_text
        is entirely contained in accumulated_text.
    """
    accumulated_words = accumulated_text.split()
    new_words = new_text.split()
    
    if not accumulated_words or not new_words:
        return new_text
    
    # Try to find overlap at the end of accumulated text
    max_overlap = min(len(accumulated_words), len(new_words))
    
    for overlap_size in range(max_overlap, 0, -1):
        # Check if the last 'overlap_size' words of accumulated_text
        # match the first 'overlap_size' words of new_text
        if accumulated_words[-overlap_size:] == new_words[:overlap_size]:
            # Found overlap! Return the non-overlapping part
            non_overlap = new_words[overlap_size:]
            if non_overlap:
                return " ".join(non_overlap)
            else:
                # new_text is entirely contained in accumulated_text
                return None
    
    # No overlap found
    return new_text


def format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def strip_vtt_tags(line: str) -> str:
    """Remove VTT-specific tags from a line."""
    line = re.sub(r"<(?:\d{2}:)?\d{2}:\d{2}\.\d{3}>", "", line)
    line = re.sub(r"<v\s+([^>]+)>", r"\1: ", line)
    line = re.sub(r"</v>", "", line)
    line = re.sub(r"</?[^>]+>", "", line)
    return line


def normalize_caption_text(lines: Sequence[str]) -> str:
    """Normalize caption text by removing tags and whitespace."""
    text = " ".join(lines)
    text = strip_vtt_tags(text)
    text = html.unescape(text)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_vtt_cues(vtt_text: str) -> List[Cue]:
    """Parse VTT text into a list of Cue objects."""
    lines = vtt_text.splitlines()
    cues: List[Cue] = []
    i = 0
    skip_block = False

    while i < len(lines):
        line = lines[i].strip("\ufeff").strip()
        upper = line.upper()

        if not line:
            skip_block = False
            i += 1
            continue

        if upper.startswith(("WEBVTT", "KIND:", "LANGUAGE:", "X-TIMESTAMP-MAP")):
            i += 1
            continue

        if upper.startswith(("NOTE", "STYLE", "REGION")):
            skip_block = True
            i += 1
            continue

        if skip_block:
            i += 1
            continue

        match = TIMING_RE.search(line)
        if not match:
            i += 1
            continue

        start = parse_timestamp(match.group("start"))
        end = parse_timestamp(match.group("end"))

        i += 1
        text_lines: List[str] = []

        while i < len(lines):
            text_line = lines[i].strip()
            if not text_line:
                break
            text_lines.append(text_line)
            i += 1

        text = normalize_caption_text(text_lines)
        if text:
            cues.append(Cue(start=start, end=end, text=text))

        i += 1

    return cues


def dedupe_cues(cues: List[Cue], mode: str) -> List[Cue]:
    """Remove duplicate cues based on the specified mode.
    
    Args:
        cues: List of Cue objects to deduplicate.
        mode: Deduplication mode - "none", "consecutive", "consecutive-overlap", or "global".
    
    Returns:
        Deduplicated list of Cue objects.
    
    Raises:
        AppError: If an unsupported dedupe mode is provided.
    """
    if mode == "none":
        return cues

    if mode == "consecutive":
        # Remove consecutive duplicate text (exact string comparison)
        result = []
        previous = None
        for cue in cues:
            if cue.text != previous:
                result.append(cue)
            previous = cue.text
        return result

    if mode == "consecutive-overlap":
        # Remove consecutive duplicates AND word-level overlap between adjacent cues
        # This handles rolling captions where each cue partially repeats the previous one
        result = []
        accumulated_text = ""  # Track ALL text processed so far
        
        for cue in cues:
            current_text = cue.text
            
            # Find overlap with all accumulated text
            new_text = find_overlap(accumulated_text, current_text)
            
            if new_text is None:
                # This cue adds nothing new (it's entirely a repeat)
                continue
            
            # Add the new text to result
            if new_text:
                result.append(Cue(start=cue.start, end=cue.end, text=new_text))
                accumulated_text += " " + new_text
                accumulated_text = accumulated_text.strip()
            elif current_text.strip():
                # Edge case: no overlap but add current text anyway
                result.append(Cue(start=cue.start, end=cue.end, text=current_text))
                accumulated_text += " " + current_text
                accumulated_text = accumulated_text.strip()
        
        return result


    if mode == "global":
        # Remove all duplicate text globally (keeps first occurrence only)
        result = []
        seen = set()
        for cue in cues:
            if cue.text not in seen:
                seen.add(cue.text)
                result.append(cue)
        return result

    raise AppError(f"Unsupported dedupe mode: {mode}")



def cues_to_blocks(cues: List[Cue], merge_paragraphs: bool) -> List[Block]:
    """Convert cues to blocks, optionally merging paragraphs."""
    if not merge_paragraphs:
        return [Block(start=cue.start, end=cue.end, text=cue.text) for cue in cues]

    blocks: List[Block] = []
    current: List[Cue] = []
    speaker_re = re.compile(r"^[A-ZÆØÅa-zæøå0-9 ._-]{1,40}:\s+")

    def flush() -> None:
        nonlocal current
        if not current:
            return
        blocks.append(
            Block(
                start=current[0].start,
                end=current[-1].end,
                text=" ".join(cue.text for cue in current).strip(),
            )
        )
        current = []

    for cue in cues:
        if speaker_re.match(cue.text) and current:
            flush()

        current.append(cue)

        if re.search(r"[.!?…][\"')\]]?$", cue.text):
            flush()

    flush()
    return blocks


def assign_chapters(blocks: List[Block], chapters: List[dict]) -> List[Block]:
    """Assign chapter titles to blocks based on timing."""
    if not chapters:
        return blocks

    normalized = []
    for idx, chapter in enumerate(chapters):
        start = float(chapter.get("start_time") or 0)
        if chapter.get("end_time") is not None:
            end = float(chapter["end_time"])
        elif idx + 1 < len(chapters):
            end = float(chapters[idx + 1].get("start_time") or 0)
        else:
            end = float("inf")

        normalized.append(
            {
                "title": chapter.get("title") or f"Chapter {idx + 1}",
                "start": start,
                "end": end,
            }
        )

    for block in blocks:
        for chapter in normalized:
            if chapter["start"] <= block.start < chapter["end"]:
                block.chapter_title = chapter["title"]
                break

    return blocks


def render_txt(blocks: List[Block], with_timestamps: bool) -> str:
    """Render blocks as plain text."""
    parts = []
    for block in blocks:
        prefix = f"[{format_timestamp(block.start)}] " if with_timestamps else ""
        parts.append(prefix + block.text)
    return "\n\n".join(parts).strip() + "\n"


def render_md(
    blocks: List[Block],
    with_timestamps: bool,
    title: str,
    chapter_title: Optional[str] = None,
) -> str:
    """Render blocks as Markdown."""
    lines = [f"# {title}", ""]
    if chapter_title:
        lines += [f"## {chapter_title}", ""]

    for block in blocks:
        prefix = f"`{format_timestamp(block.start)}` " if with_timestamps else ""
        lines.append(prefix + block.text)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_json(
    blocks: List[Block],
    info: VideoInfo,
    with_timestamps: bool,
    chapter_title: Optional[str] = None,
) -> str:
    """Render blocks as JSON."""
    data = {
        "video_id": info.video_id,
        "title": info.title,
        "url": info.webpage_url,
        "chapter": chapter_title,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "blocks": [],
    }

    for block in blocks:
        item = {
            "text": block.text,
            "chapter": block.chapter_title,
        }
        if with_timestamps:
            item["start"] = format_timestamp(block.start)
            item["end"] = format_timestamp(block.end)
            item["start_seconds"] = block.start
            item["end_seconds"] = block.end
        data["blocks"].append(item)

    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def render_csv(blocks: List[Block], with_timestamps: bool) -> str:
    """Render blocks as CSV."""
    output = io.StringIO()
    fieldnames = ["chapter", "text"]

    if with_timestamps:
        fieldnames = ["start", "end", "start_seconds", "end_seconds"] + fieldnames

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for block in blocks:
        row = {
            "chapter": block.chapter_title or "",
            "text": block.text,
        }
        if with_timestamps:
            row.update(
                {
                    "start": format_timestamp(block.start),
                    "end": format_timestamp(block.end),
                    "start_seconds": f"{block.start:.3f}",
                    "end_seconds": f"{block.end:.3f}",
                }
            )
        writer.writerow(row)

    return output.getvalue()


def render_output(
    fmt: str,
    blocks: List[Block],
    info: VideoInfo,
    with_timestamps: bool,
    chapter_title: Optional[str] = None,
) -> str:
    """Render blocks in the specified format."""
    if fmt == "txt":
        return render_txt(blocks, with_timestamps)
    if fmt == "md":
        return render_md(blocks, with_timestamps, info.title, chapter_title)
    if fmt == "json":
        return render_json(blocks, info, with_timestamps, chapter_title)
    if fmt == "csv":
        return render_csv(blocks, with_timestamps)
    raise AppError(f"Unsupported output format: {fmt}")


def extension_for_format(fmt: str) -> str:
    """Get the file extension for a given format."""
    return {
        "txt": ".txt",
        "md": ".md",
        "json": ".json",
        "csv": ".csv",
    }[fmt]


def group_blocks_by_chapter(
    blocks: List[Block],
    chapters: List[dict],
) -> List[Tuple[str, List[Block]]]:
    """Group blocks by their assigned chapters."""
    if not chapters:
        return [("Transcript", blocks)]

    result = []
    for idx, chapter in enumerate(chapters):
        title = chapter.get("title") or f"Chapter {idx + 1}"
        chapter_blocks = [block for block in blocks if block.chapter_title == title]
        if chapter_blocks:
            result.append((title, chapter_blocks))

    unassigned = [block for block in blocks if not block.chapter_title]
    if unassigned:
        result.append(("Unassigned", unassigned))

    return result or [("Transcript", blocks)]


def write_outputs(
    blocks: List[Block],
    info: VideoInfo,
    outdir: Path,
    output_name: Optional[str],
    fmt: str,
    with_timestamps: bool,
    chapter_split: bool,
) -> List[Path]:
    """Write output files in the specified format."""
    outdir.mkdir(parents=True, exist_ok=True)
    ext = extension_for_format(fmt)
    written: List[Path] = []

    if output_name:
        base = sanitize_filename(Path(output_name).stem, fallback=info.video_id)
    else:
        base = sanitize_filename(info.title, fallback=info.video_id)

    if not chapter_split:
        path = outdir / f"{base}{ext}"
        path.write_text(
            render_output(fmt, blocks, info, with_timestamps),
            encoding="utf-8",
            newline="" if fmt == "csv" else None,
        )
        return [path]

    chapter_dir = outdir / f"{base}.chapters"
    chapter_dir.mkdir(parents=True, exist_ok=True)

    chapter_groups = group_blocks_by_chapter(blocks, info.chapters)

    for idx, (chapter_title, chapter_blocks) in enumerate(chapter_groups, start=1):
        filename = f"{idx:03d}-{sanitize_filename(chapter_title, fallback='chapter')}{ext}"
        path = chapter_dir / filename
        path.write_text(
            render_output(fmt, chapter_blocks, info, with_timestamps, chapter_title),
            encoding="utf-8",
            newline="" if fmt == "csv" else None,
        )
        written.append(path)

    return written


def write_summary_template(
    paths: List[Path],
    info: VideoInfo,
    outdir: Path,
) -> Path:
    """Write a summary prompt template file."""
    prompt_path = outdir / f"{sanitize_filename(info.title, fallback=info.video_id)}.summary_prompt.md"

    transcript_list = "\n".join(f"- `{path}`" for path in paths)

    content = f"""# Summary prompt

Video: {info.title}
URL: {info.webpage_url}

Transcript file(s):

{transcript_list}

Please summarize this transcript for technical review.

Focus on:

- Main concepts
- Commands, code, APIs or configuration mentioned
- Important caveats
- Actionable follow-up items
"""

    prompt_path.write_text(content, encoding="utf-8")
    return prompt_path


def read_url_file(path: Path) -> List[str]:
    """Read URLs from a file, one per line."""
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(normalize_url_or_id(line))

    if not urls:
        raise AppError(f"No URLs found in {path}")

    return urls


def process_one_url(
    ytdlp: List[str],
    url: str,
    options: ProcessOptions,
    log_callback: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> List[Path]:
    """Process a single URL and return the paths of written files."""
    if log_callback:
        log_callback(f"Processing: {url}")
        log_callback(f"Deduplication mode: {options.dedupe}")  # Add this line

    langs = options.langs
    outdir = options.outdir.expanduser().resolve()

    info = get_video_info(ytdlp, url, options)
    if log_callback:
        log_callback(f"Video: {info.title}")
        log_callback(f"Video ID: {info.video_id}")

    vtt_path, source_kind = download_subtitles(
        ytdlp=ytdlp,
        url=url,
        outdir=outdir,
        info=info,
        langs=langs,
        options=options,
        log_callback=log_callback,
    )

    if log_callback:
        log_callback(f"Subtitle source: {source_kind}")
        log_callback(f"VTT file: {vtt_path}")

    raw_vtt = vtt_path.read_text(encoding="utf-8", errors="replace")
    cues = parse_vtt_cues(raw_vtt)
    
    if log_callback:
        log_callback(f"Parsed {len(cues)} subtitle cues before deduplication")
    
    cues = dedupe_cues(cues, options.dedupe)
    
    if log_callback:
        log_callback(f"After deduplication: {len(cues)} subtitle cues")  # Add this line

    if not cues:
        raise AppError("Subtitle file was downloaded, but no readable cues were found.")

    if log_callback:
        log_callback(f"Processing {len(cues)} subtitle cues into blocks")

    blocks = cues_to_blocks(cues, merge_paragraphs=not options.no_merge)
    blocks = assign_chapters(blocks, info.chapters)

    if log_callback:
        log_callback(f"Created {len(blocks)} text blocks")

    paths = write_outputs(
        blocks=blocks,
        info=info,
        outdir=outdir,
        output_name=options.output_name,
        fmt=options.fmt,
        with_timestamps=options.with_timestamps,
        chapter_split=options.chapter_split,
    )

    if options.summary_template:
        prompt_path = write_summary_template(paths, info, outdir)
        paths.append(prompt_path)
        if log_callback:
            log_callback(f"Created summary template: {prompt_path}")

    for path in paths:
        if log_callback:
            log_callback(f"Output: {path}")

    if not options.keep_vtt:
        try:
            workdir = vtt_path.parent
            for file in workdir.glob("*"):
                file.unlink()
            workdir.rmdir()
            if log_callback:
                log_callback("Cleaned up temporary VTT files")
        except OSError:
            pass

    return paths


def process_urls(
    urls: List[str],
    options: ProcessOptions,
    log_callback: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> List[Path]:
    """Process multiple URLs with the given options.

    Args:
        urls: List of YouTube URLs or video IDs to process.
        options: Processing options.
        log_callback: Optional callback for progress messages.
        cancel_event: Optional threading event for cancellation.

    Returns:
        List of paths to created output files.

    Raises:
        AppError: If processing fails.
    """
    if log_callback:
        log_callback("Starting YouTube subtitle processing")

    ytdlp = find_ytdlp_command()
    if log_callback:
        log_callback(f"Using yt-dlp: {' '.join(ytdlp)}")

    all_paths: List[Path] = []

    for idx, url in enumerate(urls, start=1):
        if cancel_event and cancel_event.is_set():
            if log_callback:
                log_callback("Cancellation requested")
            break

        if len(urls) > 1 and log_callback:
            log_callback(f"\n[{idx}/{len(urls)}]")

        if options.list_subs:
            list_subtitles(ytdlp, url, options, log_callback)
            continue

        try:
            paths = process_one_url(
                ytdlp=ytdlp,
                url=url,
                options=options,
                log_callback=log_callback,
                cancel_event=cancel_event,
            )
            all_paths.extend(paths)
        except AppError as e:
            if log_callback:
                log_callback(f"Error processing {url}: {e}")
            raise

    if log_callback:
        if all_paths:
            log_callback(f"\nCompleted. Created {len(all_paths)} output file(s)")
        else:
            log_callback("Completed. No output files created")

    return all_paths