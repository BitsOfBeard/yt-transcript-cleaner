#!/usr/bin/env python3
"""CLI module for YouTube subtitle cleaner.

This module provides the command-line interface for the YouTube subtitle
cleaner. It uses argparse for option parsing and preserves the original
prompt-based behavior when options are omitted.
"""

import argparse
from pathlib import Path
from typing import List

from .core import (
    AppError,
    DEFAULT_LANG_PRIORITY,
    OUTPUT_FORMATS,
    ProcessOptions,
    process_urls,
    read_url_file,
    normalize_url_or_id,
)


def prompt_nonempty(question: str) -> str:
    """Prompt the user for a non-empty response."""
    while True:
        answer = input(question).strip()
        if answer:
            return answer
        print("Please enter a value.")


def prompt_yes_no(question: str, default: bool) -> bool:
    """Prompt the user for a yes/no response."""
    default_label = "Y/n" if default else "y/N"

    while True:
        answer = input(f"{question} [{default_label}]: ").strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please answer Y or N.")


def prompt_choice(question: str, choices: List[str], default: str) -> str:
    """Prompt the user to choose from a list of options."""
    choice_list = "/".join(choices)

    while True:
        answer = input(f"{question} [{choice_list}] default {default}: ").strip().lower()
        if not answer:
            return default
        if answer in choices:
            return answer
        print(f"Please choose one of: {', '.join(choices)}")


def parse_langs(value: str | None) -> List[str]:
    """Parse a comma-separated list of language codes."""
    if not value:
        return DEFAULT_LANG_PRIORITY[:]

    langs = [item.strip() for item in value.split(",") if item.strip()]
    if not langs:
        raise AppError("No valid language codes were provided.")
    return langs


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Download YouTube subtitles with yt-dlp and clean them into readable transcripts."
    )

    parser.add_argument("-u", "--url", help="YouTube video URL or bare 11-character video ID.")
    parser.add_argument("--url-file", help="Explicit batch mode. One URL or video ID per line.")
    parser.add_argument("-l", "--langs", help=f"Subtitle language priority. Default: {','.join(DEFAULT_LANG_PRIORITY)}")
    parser.add_argument("-o", "--outdir", default=".", help="Output directory. Default: current directory.")
    parser.add_argument("--output-name", help="Output filename for single-video runs.")

    parser.add_argument(
        "--format",
        choices=OUTPUT_FORMATS,
        help="Output format. If omitted, you will be prompted.",
    )

    timestamp_group = parser.add_mutually_exclusive_group()
    timestamp_group.add_argument("--with-timestamps", dest="with_timestamps", action="store_true")
    timestamp_group.add_argument("--no-timestamps", dest="with_timestamps", action="store_false")
    parser.set_defaults(with_timestamps=None)

    chapter_group = parser.add_mutually_exclusive_group()
    chapter_group.add_argument(
        "--chapter-split",
        dest="chapter_mode",
        action="store_const",
        const="files",
        help="Split output into per-chapter files.",
    )
    chapter_group.add_argument(
        "--chapter-inline",
        dest="chapter_mode",
        action="store_const",
        const="inline",
        help="Keep a single file but insert chapter sections/headings.",
    )
    chapter_group.add_argument(
        "--no-chapter-split",
        dest="chapter_mode",
        action="store_const",
        const="none",
        help="Do not split by chapters (default).",
    )
    parser.set_defaults(chapter_mode=None)


    parser.add_argument("--no-auto", action="store_true", help="Do not use auto-generated subtitles as fallback.")
    parser.add_argument(
        "--dedupe",
        choices=["consecutive", "consecutive-overlap", "global", "none"],
        default="consecutive",
        help="Duplicate removal mode. Default: consecutive. Use consecutive-overlap for YouTube auto-generated subtitles with rolling captions.",
    )

    parser.add_argument("--no-merge", action="store_true", help="Keep one cleaned block per caption.")
    parser.add_argument("--keep-vtt", action="store_true", help="Keep the downloaded .vtt working directory.")

    parser.add_argument("--list-subs", action="store_true", help="Explicitly list available subtitles and exit.")
    parser.add_argument("--summary-template", action="store_true", help="Explicitly generate a Markdown summary prompt.")
    parser.add_argument("--cookies-from-browser", help="Explicitly pass cookies from browser, e.g. firefox or chrome.")

    parser.add_argument("--quiet", action="store_true", help="Print nothing unless an error occurs.")
    parser.add_argument("--verbose", action="store_true", help="Print yt-dlp commands and progress details.")

    return parser.parse_args()


def resolve_promptable_options(args: argparse.Namespace) -> tuple[str, bool, str]:
    """Resolve options that may be prompted for if not provided.

    Returns:
        (fmt, with_timestamps, chapter_mode)
    """
    if args.quiet and (
        args.format is None
        or args.with_timestamps is None
        or args.chapter_mode is None
    ):
        raise AppError(
            "--quiet requires --format, --with-timestamps/--no-timestamps, "
            "--chapter-split/--chapter-inline/--no-chapter-split."
        )

    fmt = args.format
    if fmt is None:
        fmt = prompt_choice("Output format?", OUTPUT_FORMATS, default="txt")

    with_timestamps = args.with_timestamps
    if with_timestamps is None:
        with_timestamps = prompt_yes_no("Include timestamps?", default=True)

    chapter_mode = args.chapter_mode
    if chapter_mode is None:
        split = prompt_yes_no("Split transcript by chapters when available?", default=False)
        chapter_mode = "files" if split else "none"

    return fmt, with_timestamps, chapter_mode

def main() -> int:
    """Main entry point for the CLI."""
    args = parse_args()

    def simple_log(message: str) -> None:
        """Simple log callback that prints to stdout/stderr."""
        if not args.quiet:
            print(message)

    try:
        if args.url and args.url_file:
            raise AppError("Use either --url or --url-file, not both.")

        if args.url_file and args.output_name:
            raise AppError("--output-name is only supported for single-video runs.")

        if args.url_file:
            urls = read_url_file(Path(args.url_file).expanduser())
        elif args.url:
            urls = [normalize_url_or_id(args.url)]
        else:
            urls = [normalize_url_or_id(prompt_nonempty("Please paste the YouTube video URL or ID: "))]

        if args.list_subs:
            list_urls = urls
        else:
            fmt, with_timestamps, chapter_mode = resolve_promptable_options(args)
            list_urls = []


        options = ProcessOptions(
            langs=parse_langs(args.langs),
            outdir=Path(args.outdir),
            output_name=args.output_name,
            fmt=args.format or "txt",
            with_timestamps=args.with_timestamps if args.with_timestamps is not None else True,
            chapter_split=args.chapter_split if args.chapter_split is not None else False,
            no_auto=args.no_auto,
            dedupe=args.dedupe,
            no_merge=args.no_merge,
            keep_vtt=args.keep_vtt,
            list_subs=args.list_subs,
            summary_template=args.summary_template,
            cookies_from_browser=args.cookies_from_browser,
            quiet=args.quiet,
            verbose=args.verbose,
        )

        all_paths = process_urls(
            urls=urls,
            options=options,
            log_callback=simple_log if not args.quiet else None,
        )

        if not args.quiet:
            for path in all_paths:
                print(path)

        return 0

    except KeyboardInterrupt:
        print("\nCancelled.", file=stderr)
        return 130
    except AppError as exc:
        print(f"Error: {exc}", file=stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=stderr)
        return 1


def run_cli() -> int:
    """Run the CLI with sys.exit."""
    import sys
    from sys import stderr
    sys.exit(main())


if __name__ == "__main__":
    run_cli()