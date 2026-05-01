"""
GUI for YouTube Transcript Cleaner.

This module provides a tkinter-based graphical user interface for downloading
and cleaning YouTube video subtitles using yt-dlp.
"""

import os
import platform
import subprocess
import sys
import threading
import json
from pathlib import Path
from typing import List, Optional
from queue import Queue
from tkinter import ttk, filedialog, messagebox

import tkinter as tk

from .core import (
    DEFAULT_LANG_PRIORITY,
    OUTPUT_FORMATS,
    ProcessOptions,
    process_urls,
)

# Dark mode colors
DARK_BG = "#2b2b2b"
DARK_FG = "#e0e0e0"
DARK_ENTRY_BG = "#3b3b3b"
DARK_ENTRY_FG = "#ffffff"
DARK_BUTTON_BG = "#404040"
DARK_BUTTON_FG = "#ffffff"
DARK_BUTTON_HOVER = "#505050"
DARK_FRAME_BG = "#333333"
DARK_SELECT_BG = "#0078d4"
DARK_SELECT_FG = "#ffffff"

# Light mode colors (for reference/to toggle back)
LIGHT_BG = "#f0f0f0"
LIGHT_FG = "#000000"

# Config file path
CONFIG_FILE = Path.home() / ".yt_transcript_cleaner_config.json"


class TranscriptCleanerApp(tk.Tk):
    """Main application window for the transcript cleaner GUI."""

    def __init__(self) -> None:
        """Initialize the application."""
        super().__init__()
        self.title("YouTube Transcript Cleaner")
        self.geometry("900x700")
        self.minsize(700, 600)

        self.queue: Queue[tuple] = Queue()
        self.worker_thread: Optional[threading.Thread] = None
        self.cancel_event = threading.Event()
        self.running = False

        # Load config before building UI (dark_mode_var needs to exist)
        self._load_config()

        # Set up UI
        self.build_ui()

        # Configure widgets based on initial state
        self._toggle_url_file_fields()

        # Apply dark mode if enabled
        if self.dark_mode_var.get():
            self._apply_dark_mode()


        # Start queue polling
        self.after(100, self.poll_queue)
        # Save config when window closes
        self.protocol("WM_DELETE_WINDOW", self._on_closing)


    def build_ui(self) -> None:
        """Build the user interface."""
        # Configure grid weights
        self.columnconfigure(0, weight=1)
        self.rowconfigure(8, weight=1)  # Output / log area

        # Title
        title = ttk.Label(
            self,
            text="YouTube Transcript Cleaner",
            font=("Helvetica", 16, "bold"),
        )
        title.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        # Input Section
        input_frame = ttk.LabelFrame(self, text="Input")
        input_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")

        # URL or file mode toggle
        self.mode_var = tk.StringVar(value="url")
        url_radio = ttk.Radiobutton(
            input_frame,
            text="Single URL / Video ID:",
            variable=self.mode_var,
            value="url",
            command=self._toggle_url_file_fields,
        )
        url_radio.grid(row=0, column=0, padx=10, pady=10, sticky="w")

        file_radio = ttk.Radiobutton(
            input_frame,
            text="URL File (batch mode):",
            variable=self.mode_var,
            value="file",
            command=self._toggle_url_file_fields,
        )
        file_radio.grid(row=1, column=0, padx=10, pady=5, sticky="w")

        # URL Entry
        self.url_entry = ttk.Entry(input_frame, width=60)
        self.url_entry.grid(row=0, column=1, padx=10, pady=10, columnspan=2, sticky="ew")
        input_frame.columnconfigure(1, weight=1)

        # URL File Entry
        self.url_file_entry = ttk.Entry(input_frame, width=50)
        self.url_file_entry.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

        # URL File Browse
        url_file_browse = ttk.Button(
            input_frame,
            text="Browse…",
            command=self.browse_url_file,
        )
        url_file_browse.grid(row=1, column=2, padx=10, pady=5, sticky="e")

        # Main Options Section
        main_frame = ttk.LabelFrame(self, text="Main Options")
        main_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")

        # Output directory (use value from _load_config)
        ttk.Label(main_frame, text="Output Directory:").grid(
            row=0, column=0, padx=10, pady=5, sticky="w"
        )
        self.outdir_entry = ttk.Entry(main_frame, width=50)
        self.outdir_entry.insert(0, self.outdir_value)
        self.outdir_entry.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        outdir_browse = ttk.Button(
            main_frame,
            text="Browse…",
            command=self.browse_outdir,
        )
        outdir_browse.grid(row=0, column=2, padx=10, pady=5, sticky="e")

        # Output name (use value from _load_config)
        ttk.Label(main_frame, text="Output Name (optional):").grid(
            row=1, column=0, padx=10, pady=5, sticky="w"
        )
        self.output_name_entry = ttk.Entry(main_frame, width=50)
        self.output_name_entry.insert(0, self.output_name_value)
        self.output_name_entry.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

        main_frame.columnconfigure(1, weight=1)

        # Format (use var from _load_config)
        ttk.Label(main_frame, text="Output Format:").grid(
            row=2, column=0, padx=10, pady=5, sticky="w"
        )
        # format_var already created in _load_config()
        format_combo = ttk.Combobox(
            main_frame,
            textvariable=self.format_var,
            values=OUTPUT_FORMATS,
            width=47,
            state="readonly",
        )
        format_combo.grid(row=2, column=1, pady=5, padx=10, sticky="ew")

        # Timestamps (use var from _load_config)
        timestamps_check = ttk.Checkbutton(
            main_frame,
            text="Include Timestamps",
            variable=self.timestamps_var,
        )
        timestamps_check.grid(row=3, column=0, padx=10, pady=5, sticky="w")

        # Chapter Split (use var from _load_config)
        chapter_split_check = ttk.Checkbutton(
            main_frame,
            text="Split by Chapters",
            variable=self.chapter_split_var,
        )
        chapter_split_check.grid(row=3, column=1, padx=10, pady=5, sticky="w")

        # Language Priority (use value from _load_config)
        ttk.Label(main_frame, text="Language Priority (comma-separated):").grid(
            row=4, column=0, padx=10, pady=5, sticky="w"
        )
        self.langs_entry = ttk.Entry(main_frame, width=50)
        self.langs_entry.insert(0, self.langs_entry_value)
        self.langs_entry.grid(row=4, column=1, columnspan=2, padx=10, pady=5, sticky="ew")

        # Advanced Options Section
        adv_frame = ttk.LabelFrame(self, text="Advanced Options")
        adv_frame.grid(row=3, column=0, padx=20, pady=10, sticky="ew")

        # Disable auto captions (use var from _load_config)
        no_auto_check = ttk.Checkbutton(
            adv_frame,
            text="Disable Auto Captions Fallback",
            variable=self.no_auto_var,
        )
        no_auto_check.grid(row=0, column=0, padx=10, pady=5, sticky="w")

        # Dedupe mode (use var from _load_config)
        ttk.Label(adv_frame, text="Deduplication Mode:").grid(
            row=0, column=1, padx=10, pady=5, sticky="w"
        )
        # dedupe_var already created in _load_config()
        dedupe_combo = ttk.Combobox(
            adv_frame,
            textvariable=self.dedupe_var,
            values=["consecutive", "consecutive-overlap", "global", "none"],
            width=20,
            state="readonly",
        )
        dedupe_combo.grid(row=0, column=2, pady=5, padx=10, sticky="w")

        # No merge (use var from _load_config)
        no_merge_check = ttk.Checkbutton(
            adv_frame,
            text="Do Not Merge Captions",
            variable=self.no_merge_var,
        )
        no_merge_check.grid(row=1, column=0, padx=10, pady=5, sticky="w")

        # Keep VTT (use var from _load_config)
        keep_vtt_check = ttk.Checkbutton(
            adv_frame,
            text="Keep Downloaded VTT Working Directory",
            variable=self.keep_vtt_var,
        )
        keep_vtt_check.grid(row=1, column=1, padx=10, pady=5, sticky="w")

        # List subtitles (use var from _load_config)
        list_subs_check = ttk.Checkbutton(
            adv_frame,
            text="List Subtitles and Exit",
            variable=self.list_subs_var,
        )
        list_subs_check.grid(row=2, column=0, padx=10, pady=5, sticky="w")

        # Summary template (use var from _load_config)
        summary_template_check = ttk.Checkbutton(
            adv_frame,
            text="Generate Summary Prompt",
            variable=self.summary_template_var,
        )
        summary_template_check.grid(row=2, column=1, padx=10, pady=5, sticky="w")

        # Cookies from browser (use value from _load_config)
        ttk.Label(adv_frame, text="Cookies from Browser:").grid(
            row=2, column=2, padx=10, pady=5, sticky="w"
        )
        self.cookies_entry = ttk.Entry(adv_frame, width=20)
        self.cookies_entry.insert(0, self.cookies_entry_value)
        self.cookies_entry.grid(row=2, column=3, pady=5, padx=10, sticky="w")

        # Quiet (use var from _load_config)
        quiet_check = ttk.Checkbutton(
            adv_frame,
            text="Quiet Mode",
            variable=self.quiet_var,
        )
        quiet_check.grid(row=3, column=0, padx=10, pady=5, sticky="w")

        # Verbose (use var from _load_config)
        verbose_check = ttk.Checkbutton(
            adv_frame,
            text="Verbose",
            variable=self.verbose_var,
        )
        verbose_check.grid(row=3, column=1, padx=10, pady=5, sticky="w")

        # Dark Mode (use variable created in __init__ by _load_config)
        dark_mode_check = ttk.Checkbutton(
            adv_frame,
            text="Dark Mode (requires restart to take full effect)",
            variable=self.dark_mode_var,
            command=self._toggle_dark_mode,
        )
        dark_mode_check.grid(row=3, column=2, padx=10, pady=5, sticky="w")

        # Action Buttons

        button_frame = ttk.Frame(self)
        button_frame.grid(row=4, column=0, padx=20, pady=10, sticky="ew")

        self.start_button = ttk.Button(button_frame, text="Start", command=self.start, width=15)
        self.start_button.grid(row=0, column=0, padx=10, pady=5)

        self.cancel_button = ttk.Button(button_frame, text="Cancel", command=self.cancel, width=15, state="disabled")
        self.cancel_button.grid(row=0, column=1, padx=10, pady=5)

        self.open_folder_button = ttk.Button(button_frame, text="Open Output Folder", command=self.open_output_folder, width=20)
        self.open_folder_button.grid(row=0, column=2, padx=10, pady=5)

        # Output / Log Section
        log_frame = ttk.LabelFrame(self, text="Log")
        log_frame.grid(row=5, column=0, padx=20, pady=10, sticky="nsew")
        self.rowconfigure(5, weight=1)

        self.log_text = tk.Text(log_frame, wrap="word", state="disabled", height=15)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        # Status Line
        self.status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w")
        status_label.grid(row=6, column=0, padx=20, pady=10, sticky="ew")


    def _toggle_url_file_fields(self) -> None:
        """Toggle URL and URL file fields based on mode."""
        mode = self.mode_var.get()
        if mode == "url":
            self.url_entry.configure(state="normal")
            self.url_file_entry.configure(state="disabled")
        else:
            self.url_entry.configure(state="disabled")
            self.url_file_entry.configure(state="normal")

    def browse_outdir(self) -> None:
        """Browse for output directory."""
        path = filedialog.askdirectory(title="Select Output Directory")
        if path:
            self.outdir_entry.delete(0, tk.END)
            self.outdir_entry.insert(0, path)

    def browse_url_file(self) -> None:
        """Browse for URL file."""
        path = filedialog.askopenfilename(
            title="Select URL File",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
        )
        if path:
            self.url_file_entry.delete(0, tk.END)
            self.url_file_entry.insert(0, path)

    def validate_form(self) -> List[str]:
        """Validate the form and return list of errors."""
        errors = []

        mode = self.mode_var.get()
        url = self.url_entry.get().strip()
        url_file = self.url_file_entry.get().strip()

        if mode == "url":
            if not url:
                errors.append("URL or video ID is required.")
            if url_file:
                errors.append("URL file cannot be used in single URL mode.")
        else:
            if not url_file :
                errors.append("URL file is required for batch mode.")
            if url:
                errors.append("URL cannot be used in batch mode.")

        outdir = self.outdir_entry.get().strip()
        if not outdir:
            errors.append("Output directory is required.")

        output_name = self.output_name_entry.get().strip()
        if output_name and mode != "url":
            errors.append("Output name can only be used for single URL mode.")

        fmt = self.format_var.get()
        if fmt not in OUTPUT_FORMATS:
            errors.append(f"Format must be one of: {', '.join(OUTPUT_FORMATS)}")

        dedupe = self.dedupe_var.get()
        if dedupe not in ("consecutive", "consecutive-overlap", "global", "none"):
            errors.append("Deduplication mode must be one of: consecutive, consecutive-overlap, global, none")

        return errors

    def build_options(self) -> ProcessOptions:
        """Build ProcessOptions from form values."""
        langs_str = self.langs_entry.get().strip()
        langs = [lang.strip() for lang in langs_str.split(",") if lang.strip()]
        if not langs:
            langs = DEFAULT_LANG_PRIORITY[:]

        return ProcessOptions(
            langs=langs,
            outdir=Path(self.outdir_entry.get().strip()),
            output_name=self.output_name_entry.get().strip() or None,
            fmt=self.format_var.get(),
            with_timestamps=self.timestamps_var.get(),
            chapter_split=self.chapter_split_var.get(),
            no_auto=self.no_auto_var.get(),
            dedupe=self.dedupe_var.get(),
            no_merge=self.no_merge_var.get(),
            keep_vtt=self.keep_vtt_var.get(),
            list_subs=self.list_subs_var.get(),
            summary_template=self.summary_template_var.get(),
            cookies_from_browser=self.cookies_entry.get().strip() or None,
            quiet=self.quiet_var.get(),
            verbose=self.verbose_var.get(),
        )

    def start(self) -> None:
        """Start processing."""
        errors = self.validate_form()
        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors))
            return

        self.set_running(True)
        self.cancel_event.clear()

        # Build URLs and options
        mode = self.mode_var.get()
        if mode == "url":
            urls = [self.url_entry.get().strip()]
        else:
            url_file = Path(self.url_file_entry.get().strip())
            with url_file.open(encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

        options = self.build_options()

        # Start worker thread
        self.worker_thread = threading.Thread(
            target=self.worker,
            args=(urls, options),
            daemon=True,
        )
        self.worker_thread.start()

    def cancel(self) -> None:
        """Cancel processing."""
        if self.running:
            self.cancel_event.set()
            self.log("Cancellation requested...")

        self.set_running(False)

    def worker(self, urls: List[str], options: ProcessOptions) -> None:
        """Worker thread processing function."""
        try:
            def log_callback(message: str) -> None:
                self.queue.put(("log", message))

            result_paths = process_urls(
                urls=urls,
                options=options,
                log_callback=log_callback,
                cancel_event=self.cancel_event,
            )

            if not self.cancel_event.is_set():
                self.queue.put(("done", result_paths))
                self.queue.put(("log", f"\nCompleted. Generated {len(result_paths)} file(s)."))
        except Exception:
            import traceback
            self.queue.put(("error", traceback.format_exc()))
            self.queue.put(("status", "Error"))

    def poll_queue(self) -> None:
        """Poll the queue for messages from worker thread."""
        try:
            while True:
                msg_type, msg = self.queue.get_nowait()

                if msg_type == "log":
                    self.log(msg)
                elif msg_type == "done":
                    for path in msg:
                        self.log(f"Output: {path}")
                    self.set_running(False)
                elif msg_type == "error":
                    self.log(f"\nERROR:\n{msg}")
                    messagebox.showerror("Error", f"An error occurred:\n\n{msg}")
                    self.set_running(False)
                elif msg_type == "status":
                    self.status_var.set(msg)

        except:
            pass  # Queue is empty

        self.after(100, self.poll_queue)

    def log(self, message: str) -> None:
        """Append a message to the log widget."""
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def set_running(self, running: bool) -> None:
        """Set the running state and update UI accordingly."""
        self.running = running

        if running:
            self.start_button.configure(state="disabled")
            self.cancel_button.configure(state="normal")
            self.status_var.set("Processing...")
        else:
            self.start_button.configure(state="normal")
            self.cancel_button.configure(state="disabled")
            self.status_var.set("Ready")

    def open_output_folder(self) -> None:
        """Open the output directory in file explorer."""
        outdir = self.outdir_entry.get().strip()
        if not outdir:
            messagebox.showwarning("Warning", "No output directory specified.")
            return

        path = Path(outdir)
        if not path.exists():
            messagebox.showwarning("Warning", f"Output directory does not exist:\n{path}")
            return

        path_str = str(path)

        if platform.system() == "Windows":
            os.startfile(path_str)
        elif platform.system() == "Darwin":  # macOS
            subprocess.run(["open", path_str], check=True)
        else:  # Linux/Unix
            subprocess.run(["xdg-open", path_str], check=True)

    def _toggle_dark_mode(self) -> None:
        """Toggle between dark and light mode."""
        if self.dark_mode_var.get():
            self._apply_dark_mode()
        else:
            self._apply_light_mode()
        # Save the preference
        self._save_config()


    def _apply_dark_mode(self) -> None:
        """Apply dark mode colors to ttk styles."""
        try:
            style = ttk.Style()
            style.theme_use('clam')
            
            # Configure frame style
            style.configure("TFrame", background=DARK_BG)
            style.configure("TLabelframe", background=DARK_BG, foreground=DARK_FG)
            style.configure("TLabelframe.Label", background=DARK_BG, foreground=DARK_FG)
            
            # Configure label style
            style.configure("TLabel", background=DARK_BG, foreground=DARK_FG)
            style.configure("TCheckbutton", background=DARK_BG, foreground=DARK_FG)
            style.configure("TRadiobutton", background=DARK_BG, foreground=DARK_FG)
            
            # Configure button style
            style.configure("TButton", background=DARK_BUTTON_BG, foreground=DARK_BUTTON_FG, borderwidth=1)
            style.map("TButton", background=[("active", DARK_BUTTON_HOVER), ("pressed", DARK_BUTTON_HOVER)])
            
            # Configure entry style
            style.configure("TEntry", fieldbackground=DARK_ENTRY_BG, foreground=DARK_ENTRY_FG, insertcolor=DARK_FG)
            
            # Configure combobox style
            style.configure("TCombobox", fieldbackground=DARK_ENTRY_BG, foreground=DARK_ENTRY_FG, background=DARK_BG)
            style.map("TCombobox", selectbackground=[("readonly", DARK_SELECT_BG)], selectforeground=[("readonly", DARK_SELECT_FG)])
            
            # Configure scrollbar
            style.configure("TScrollbar", background=DARK_FRAME_BG, troughcolor=DARK_BG, bordercolor=DARK_BG, darkcolor=DARK_BG, lightcolor=DARK_BG)
            
            # Configure label frame
            style.configure("TLabelframe", background=DARK_BG, foreground=DARK_FG)
            style.configure("TLabelframe.Label", background=DARK_BG, foreground=DARK_FG)
            
            # Configure radiobutton
            style.configure("TRadiobutton", background=DARK_BG, foreground=DARK_FG)
            
            self.configure(bg=DARK_BG)
            self.log_text.configure(bg=DARK_ENTRY_BG, fg=DARK_ENTRY_FG, insertbackground=DARK_FG)
            
        except Exception as e:
            print(f"Error applying dark mode: {e}")

    def _apply_light_mode(self) -> None:
        """Apply light mode colors (restore defaults)."""
        try:
            style = ttk.Style()
            # Try to restore Windows native theme if on Windows, otherwise use 'default'
            if platform.system() == "Windows":
                try:
                    style.theme_use('vista')
                except:
                    try:
                        style.theme_use('winnative')
                    except:
                        style.theme_use('clam')
            else:
                style.theme_use('default')
            
            # Reset to defaults
            style.configure("TFrame", background="")
            style.configure("TLabelframe", background="", foreground="")
            style.configure("TLabelframe.Label", background="", foreground="")
            style.configure("TLabel", background="", foreground="")
            style.configure("TCheckbutton", background="", foreground="")
            style.configure("TRadiobutton", background="", foreground="")
            style.configure("TButton", background="", foreground="", borderwidth="")
            style.map("TButton", background="")
            style.configure("TEntry", fieldbackground="", foreground="", insertcolor="")
            style.configure("TCombobox", fieldbackground="", foreground="", background="")
            style.map("TCombobox", selectbackground=[], selectforeground=[])
            style.configure("TScrollbar", background="")
            
            self.configure(bg="")
            self.log_text.configure(bg="", fg="", insertbackground="")
            
        except Exception as e:
            print(f"Error applying light mode: {e}")

    def _save_config(self) -> None:
        """Save configuration to file."""
        try:
            # Get output directory from the entry field
            outdir = self.outdir_entry.get().strip() if hasattr(self, 'outdir_entry') else str(Path.cwd())
            if not outdir:
                outdir = str(Path.cwd())

            # Get language priority from the entry field
            langs = self.langs_entry.get().strip() if hasattr(self, 'langs_entry') else "en-orig,en,en-US,en-GB"
            if not langs:
                langs = "en-orig,en,en-US,en-GB"

            # Get cookies from browser from the entry field
            cookies = self.cookies_entry.get().strip() if hasattr(self, 'cookies_entry') else ""

            # Get output name from the entry field
            output_name = self.output_name_entry.get().strip() if hasattr(self, 'output_name_entry') else ""

            config = {
                "dark_mode": self.dark_mode_var.get(),
                "dedupe": self.dedupe_var.get(),
                "format": self.format_var.get(),
                "with_timestamps": self.timestamps_var.get(),
                "chapter_split": self.chapter_split_var.get(),
                "no_auto": self.no_auto_var.get(),
                "no_merge": self.no_merge_var.get(),
                "keep_vtt": self.keep_vtt_var.get(),
                "list_subs": self.list_subs_var.get(),
                "summary_template": self.summary_template_var.get(),
                "quiet": self.quiet_var.get(),
                "verbose": self.verbose_var.get(),
                "langs": langs,
                "cookies_from_browser": cookies,
                "output_name": output_name,
                "outdir": outdir,
            }
            with CONFIG_FILE.open("w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")


    def _load_config(self) -> None:
        """Load configuration from file and create all Var objects."""
        # Default values
        config_defaults = {
            "dark_mode": False,
            "dedupe": "consecutive",
            "format": "txt",
            "with_timestamps": True,
            "chapter_split": False,
            "no_auto": False,
            "no_merge": False,
            "keep_vtt": False,
            "list_subs": False,
            "summary_template": False,
            "quiet": False,
            "verbose": False,
            "langs": "en-orig,en,en-US,en-GB",
            "outdir": str(Path.cwd()),
            "cookies_from_browser": "",
            "output_name": "",
        }

        # Load from config file if it exists
        if CONFIG_FILE.exists():
            try:
                with CONFIG_FILE.open("r", encoding="utf-8") as f:
                    loaded_config = json.load(f)
                    # Update defaults with loaded values
                    config_defaults.update(loaded_config)
            except Exception as e:
                print(f"Error loading config: {e}")

        # Create all Var objects based on loaded/default values
        self.dark_mode_var = tk.BooleanVar(value=config_defaults["dark_mode"])
        self.dedupe_var = tk.StringVar(value=config_defaults["dedupe"])
        self.format_var = tk.StringVar(value=config_defaults["format"])
        self.timestamps_var = tk.BooleanVar(value=config_defaults["with_timestamps"])
        self.chapter_split_var = tk.BooleanVar(value=config_defaults["chapter_split"])
        self.no_auto_var = tk.BooleanVar(value=config_defaults["no_auto"])
        self.no_merge_var = tk.BooleanVar(value=config_defaults["no_merge"])
        self.keep_vtt_var = tk.BooleanVar(value=config_defaults["keep_vtt"])
        self.list_subs_var = tk.BooleanVar(value=config_defaults["list_subs"])
        self.summary_template_var = tk.BooleanVar(value=config_defaults["summary_template"])
        self.quiet_var = tk.BooleanVar(value=config_defaults["quiet"])
        self.verbose_var = tk.BooleanVar(value=config_defaults["verbose"])
        self.cookies_entry_value = config_defaults["cookies_from_browser"]
        self.output_name_value = config_defaults["output_name"]
        self.outdir_value = config_defaults["outdir"]
        self.langs_entry_value = config_defaults["langs"]


    def _on_closing(self) -> None:
        """Handle window closing - save config before exit."""
        self._save_config()
        self.destroy()


def run_gui() -> int:
    """Run the GUI application."""
    app = TranscriptCleanerApp()
    app.mainloop()
    return 0
