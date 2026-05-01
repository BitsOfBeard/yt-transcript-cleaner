#!/usr/bin/env python3
"""Main entry point for the yt_transcript_cleaner package.

This module provides the entry point for running the package as a module.
By default, it starts the GUI. If --cli is passed as the first argument,
it runs the CLI interface instead.
"""

import sys

from . import __version__
from .gui import run_gui
from .cli import run_cli


def main() -> int:
    """Main entry point."""
    # Check if --cli is the first argument
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        # Remove --cli from arguments and pass the rest to CLI
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        return run_cli()
    else:
        # Default to GUI
        return run_gui()


if __name__ == "__main__":
    sys.exit(main())