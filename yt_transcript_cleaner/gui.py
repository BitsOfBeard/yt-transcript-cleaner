"""
PySide6 GUI for YouTube Transcript Cleaner.

This module provides a Qt-based graphical user interface for downloading
and cleaning YouTube video subtitles using yt-dlp.
"""

import json
import os
import platform
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
    QLayout,
)

from .core import (
    DEFAULT_LANG_PRIORITY,
    OUTPUT_FORMATS,
    ProcessOptions,
    process_urls,
)


CONFIG_FILE = Path.home() / ".yt_transcript_cleaner_config.json"


THEME_COLORS = {
    "light": {
        "window": "#f0f0f0",
        "panel": "#f8f8f8",
        "panel_border": "#c8c8c8",
        "text": "#000000",
        "muted": "#404040",
        "input": "#ffffff",
        "input_text": "#000000",
        "button": "#e8e8e8",
        "button_hover": "#dddddd",
        "button_pressed": "#cccccc",
        "accent": "#0078d4",
        "selection_text": "#ffffff",
        "disabled_text": "#808080",
        "log": "#ffffff",
        "titlebar": "#f0f0f0",
        "titlebar_text": "#000000",
    },
    "dark": {
        "window": "#202020",
        "panel": "#2b2b2b",
        "panel_border": "#444444",
        "text": "#e0e0e0",
        "muted": "#b0b0b0",
        "input": "#303030",
        "input_text": "#ffffff",
        "button": "#3a3a3a",
        "button_hover": "#505050",
        "button_pressed": "#606060",
        "accent": "#0078d4",
        "selection_text": "#ffffff",
        "disabled_text": "#777777",
        "log": "#242424",
        "titlebar": "#202020",
        "titlebar_text": "#ffffff",
    },
    "oled": {
        "window": "#000000",
        "panel": "#000000",
        "panel_border": "#202020",
        "text": "#d0d0d0",
        "muted": "#a0a0a0",
        "input": "#080808",
        "input_text": "#ffffff",
        "button": "#101010",
        "button_hover": "#252525",
        "button_pressed": "#303030",
        "accent": "#1e90ff",
        "selection_text": "#ffffff",
        "disabled_text": "#606060",
        "log": "#000000",
        "titlebar": "#000000",
        "titlebar_text": "#ffffff",
    },
}


def _default_config() -> Dict[str, Any]:
    return {
        "theme": "oled",
        "dark_mode": False,
        "dedupe": "consecutive",
        "format": "txt",
        "with_timestamps": True,
        "chapter_split": False,
        "chapter_mode": "none",
        "no_auto": False,
        "no_merge": False,
        "keep_vtt": False,
        "list_subs": False,
        "summary_template": False,
        "quiet": False,
        "verbose": False,
        "langs": ",".join(DEFAULT_LANG_PRIORITY),
        "outdir": str(Path.cwd()),
        "cookies_from_browser": "",
        "output_name": "",
    }


def load_config() -> Dict[str, Any]:
    config = _default_config()
    loaded_config: Dict[str, Any] = {}

    if CONFIG_FILE.exists():
        try:
            with CONFIG_FILE.open("r", encoding="utf-8") as f:
                loaded_config = json.load(f)
            if isinstance(loaded_config, dict):
                config.update(loaded_config)
        except Exception as e:
            print(f"Error loading config: {e}")

    if "theme" not in loaded_config and "dark_mode" in loaded_config:
        config["theme"] = "dark" if loaded_config.get("dark_mode") else "light"

    if "chapter_mode" not in loaded_config:
        config["chapter_mode"] = "files" if loaded_config.get("chapter_split") else "none"

    if config.get("theme") not in ("light", "dark", "oled"):
        config["theme"] = "oled"

    if config.get("format") not in OUTPUT_FORMATS:
        config["format"] = OUTPUT_FORMATS[0]

    if config.get("dedupe") not in ("consecutive", "consecutive-overlap", "global", "none"):
        config["dedupe"] = "consecutive"

    if config.get("chapter_mode") not in ("none", "inline", "files"):
        config["chapter_mode"] = "none"

    return config


def set_combo_value(combo: QComboBox, value: str, fallback_index: int = 0) -> None:
    index = combo.findText(value)
    combo.setCurrentIndex(index if index >= 0 else fallback_index)


def qss_for_theme(theme: str) -> str:
    c = THEME_COLORS[theme]

    return f"""
    QWidget {{
        background-color: {c["window"]};
        color: {c["text"]};
        selection-background-color: {c["accent"]};
        selection-color: {c["selection_text"]};
    }}

    QMainWindow {{
        background-color: {c["window"]};
    }}

    QLabel {{
        background-color: transparent;
        color: {c["text"]};
    }}

    QLabel#TitleLabel {{
        font-size: 18px;
        font-weight: 700;
        color: {c["text"]};
    }}

    QGroupBox {{
        background-color: {c["panel"]};
        border: 1px solid {c["panel_border"]};
        border-radius: 6px;
        margin-top: 16px;
        padding: 0px;
        font-weight: 600;
    }}


    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 5px;
        color: {c["text"]};
        background-color: {c["window"]};
    }}

    QLineEdit,
    QComboBox {{
        background-color: {c["input"]};
        color: {c["input_text"]};
        border: 1px solid {c["panel_border"]};
        border-radius: 4px;
        padding-left: 6px;
        padding-right: 6px;
        padding-top: 2px;
        padding-bottom: 2px;
        selection-background-color: {c["accent"]};
        selection-color: {c["selection_text"]};
    }}

    QPlainTextEdit {{
        background-color: {c["log"]};
        color: {c["input_text"]};
        border: 1px solid {c["panel_border"]};
        border-radius: 4px;
        padding: 5px;
        font-family: Consolas, "Cascadia Mono", monospace;
        font-size: 10pt;
        selection-background-color: {c["accent"]};
        selection-color: {c["selection_text"]};
    }}

    QLineEdit:disabled,
    QComboBox:disabled {{
        color: {c["disabled_text"]};
        background-color: {c["panel"]};
    }}

    QPushButton {{
        background-color: {c["button"]};
        color: {c["text"]};
        border: 1px solid {c["panel_border"]};
        border-radius: 4px;
        padding: 6px 12px;
        min-height: 24px;
    }}

    QPushButton:hover {{
        background-color: {c["button_hover"]};
    }}

    QPushButton:pressed {{
        background-color: {c["button_pressed"]};
    }}

    QPushButton:disabled {{
        color: {c["disabled_text"]};
        background-color: {c["panel"]};
    }}

    QCheckBox,
    QRadioButton {{
        background-color: transparent;
        color: {c["text"]};
        spacing: 6px;
    }}

    QCheckBox:disabled,
    QRadioButton:disabled {{
        color: {c["disabled_text"]};
    }}

    QComboBox::drop-down {{
        border-left: 1px solid {c["panel_border"]};
        width: 24px;
        background-color: {c["button"]};
    }}

    QComboBox QAbstractItemView {{
        background-color: {c["input"]};
        color: {c["input_text"]};
        border: 1px solid {c["panel_border"]};
        selection-background-color: {c["accent"]};
        selection-color: {c["selection_text"]};
    }}

    QScrollBar:vertical {{
        background-color: {c["window"]};
        width: 14px;
        margin: 0;
    }}

    QScrollBar::handle:vertical {{
        background-color: {c["button"]};
        border-radius: 6px;
        min-height: 20px;
    }}

    QScrollBar::handle:vertical:hover {{
        background-color: {c["button_hover"]};
    }}

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    QStatusBar {{
        background-color: {c["panel"]};
        color: {c["text"]};
        border-top: 1px solid {c["panel_border"]};
    }}

    QMessageBox {{
        background-color: {c["window"]};
        color: {c["text"]};
    }}
    """


class ProcessWorker(QObject):
    log = Signal(str)
    done = Signal(object)
    error = Signal(str)
    status = Signal(str)
    finished = Signal()

    def __init__(
        self,
        urls: List[str],
        options: ProcessOptions,
        cancel_event: threading.Event,
    ) -> None:
        super().__init__()
        self.urls = urls
        self.options = options
        self.cancel_event = cancel_event

    @Slot()
    def run(self) -> None:
        try:
            def log_callback(message: str) -> None:
                self.log.emit(message)

            result_paths = process_urls(
                urls=self.urls,
                options=self.options,
                log_callback=log_callback,
                cancel_event=self.cancel_event,
            )

            if self.cancel_event.is_set():
                self.log.emit("\nCancelled.")
                self.status.emit("Cancelled")
            else:
                self.done.emit(result_paths)
                self.log.emit(f"\nCompleted. Generated {len(result_paths)} file(s).")
                self.status.emit("Ready")
        except Exception:
            self.error.emit(traceback.format_exc())
            self.status.emit("Error")
        finally:
            self.finished.emit()


class TranscriptCleanerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.config = load_config()
        self.worker_thread: Optional[QThread] = None
        self.worker: Optional[ProcessWorker] = None
        self.cancel_event = threading.Event()
        self.running = False
        self.closing_after_cancel = False

        self.setWindowTitle("YouTube Transcript Cleaner")
        self.resize(900, 700)
        # self.setMinimumSize(700, 600)  # removed: we will derive min size from layouts

        self._build_ui()
        self._load_values_into_ui()
        self._toggle_url_file_fields()
        self._apply_theme(save=False)

        # Let Qt compute the natural minimum size from layouts and widgets,
        # then use that as the true minimum so rows don’t get compressed.
        self.adjustSize()
        self.setMinimumSize(self.size())

        QTimer.singleShot(0, self._apply_windows_titlebar)


    def _configure_grid_layout(
        self,
        layout: QGridLayout,
        row_count: int,
        top_margin: int = 22,
    ) -> None:
        layout.setContentsMargins(12, top_margin, 12, 12)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        row_height = max(28, self.fontMetrics().height() + 12)

        for row in range(row_count):
            layout.setRowMinimumHeight(row, row_height)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(20, 18, 20, 12)
        root.setSpacing(10)
        root.setSizeConstraint(QVBoxLayout.SetMinimumSize)

        title = QLabel("YouTube Transcript Cleaner")
        title.setObjectName("TitleLabel")
        root.addWidget(title)

        input_group = QGroupBox("Input")
        input_layout = QGridLayout(input_group)
        self._configure_grid_layout(input_layout, row_count=2)
        input_layout.setColumnStretch(1, 1)

        self.single_url_radio = QRadioButton("Single URL / Video ID:")
        self.url_file_radio = QRadioButton("URL File (batch mode):")
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.single_url_radio)
        self.mode_group.addButton(self.url_file_radio)
        self.single_url_radio.setChecked(True)

        self.url_entry = QLineEdit()
        self.url_file_entry = QLineEdit()
        self.url_file_browse_button = QPushButton("Browse…")
        self.url_file_browse_button.clicked.connect(self.browse_url_file)

        self.single_url_radio.toggled.connect(self._toggle_url_file_fields)
        self.url_file_radio.toggled.connect(self._toggle_url_file_fields)

        input_layout.addWidget(self.single_url_radio, 0, 0)
        input_layout.addWidget(self.url_entry, 0, 1, 1, 2)
        input_layout.addWidget(self.url_file_radio, 1, 0)
        input_layout.addWidget(self.url_file_entry, 1, 1)
        input_layout.addWidget(self.url_file_browse_button, 1, 2)

        root.addWidget(input_group)

        main_group = QGroupBox("Main Options")
        main_layout = QGridLayout(main_group)
        self._configure_grid_layout(main_layout, row_count=5)
        main_layout.setColumnStretch(1, 1)

        self.outdir_entry = QLineEdit()
        self.outdir_browse_button = QPushButton("Browse…")
        self.outdir_browse_button.clicked.connect(self.browse_outdir)

        self.output_name_entry = QLineEdit()

        self.format_combo = QComboBox()
        self.format_combo.addItems(list(OUTPUT_FORMATS))

        self.timestamps_check = QCheckBox("Include Timestamps")

        self.chapter_mode_combo = QComboBox()
        self.chapter_mode_combo.addItems(["none", "inline", "files"])

        self.langs_entry = QLineEdit()

        main_layout.addWidget(QLabel("Output Directory:"), 0, 0)
        main_layout.addWidget(self.outdir_entry, 0, 1)
        main_layout.addWidget(self.outdir_browse_button, 0, 2)

        main_layout.addWidget(QLabel("Output Name (optional):"), 1, 0)
        main_layout.addWidget(self.output_name_entry, 1, 1, 1, 2)

        main_layout.addWidget(QLabel("Output Format:"), 2, 0)
        main_layout.addWidget(self.format_combo, 2, 1, 1, 2)

        main_layout.addWidget(self.timestamps_check, 3, 0)
        main_layout.addWidget(QLabel("Chapter Mode:"), 3, 1)
        main_layout.addWidget(self.chapter_mode_combo, 3, 2)

        main_layout.addWidget(QLabel("Language Priority (comma-separated):"), 4, 0)
        main_layout.addWidget(self.langs_entry, 4, 1, 1, 2)

        root.addWidget(main_group)

        advanced_group = QGroupBox("Advanced Options")
        advanced_layout = QGridLayout(advanced_group)
        self._configure_grid_layout(advanced_layout, row_count=4)
        advanced_layout.setColumnStretch(4, 1)

        self.no_auto_check = QCheckBox("Disable Auto Captions Fallback")

        self.dedupe_combo = QComboBox()
        self.dedupe_combo.addItems(["consecutive", "consecutive-overlap", "global", "none"])

        self.no_merge_check = QCheckBox("Do Not Merge Captions")
        self.keep_vtt_check = QCheckBox("Keep Downloaded VTT Working Directory")
        self.list_subs_check = QCheckBox("List Subtitles and Exit")
        self.summary_template_check = QCheckBox("Generate Summary Prompt")

        self.cookies_entry = QLineEdit()
        self.cookies_entry.setPlaceholderText("firefox, chrome, edge…")

        self.quiet_check = QCheckBox("Quiet Mode")
        self.verbose_check = QCheckBox("Verbose")

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["light", "dark", "oled"])
        self.theme_combo.currentTextChanged.connect(lambda _: self._apply_theme(save=True))

        advanced_layout.addWidget(self.no_auto_check, 0, 0)
        advanced_layout.addWidget(QLabel("Deduplication Mode:"), 0, 1)
        advanced_layout.addWidget(self.dedupe_combo, 0, 2)

        advanced_layout.addWidget(self.no_merge_check, 1, 0)
        advanced_layout.addWidget(self.keep_vtt_check, 1, 1, 1, 2)

        advanced_layout.addWidget(self.list_subs_check, 2, 0)
        advanced_layout.addWidget(self.summary_template_check, 2, 1)
        advanced_layout.addWidget(QLabel("Cookies from Browser:"), 2, 2)
        advanced_layout.addWidget(self.cookies_entry, 2, 3)

        advanced_layout.addWidget(self.quiet_check, 3, 0)
        advanced_layout.addWidget(self.verbose_check, 3, 1)
        advanced_layout.addWidget(QLabel("Theme:"), 3, 2)
        advanced_layout.addWidget(self.theme_combo, 3, 3)

        root.addWidget(advanced_group)

        button_row = QHBoxLayout()

        self.start_button = QPushButton("Start")
        self.start_button.setFixedWidth(120)
        self.start_button.clicked.connect(self.start)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setFixedWidth(120)
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)

        self.open_folder_button = QPushButton("Open Output Folder")
        self.open_folder_button.clicked.connect(self.open_output_folder)

        button_row.addWidget(self.start_button)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.open_folder_button)
        button_row.addItem(QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        root.addLayout(button_row)

        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(12, 22, 12, 12)
        log_layout.setSpacing(8)

        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)

        log_layout.addWidget(self.log_text)

        root.addWidget(log_group, 1)

        self.statusBar().showMessage("Ready")

    def _load_values_into_ui(self) -> None:
        self.outdir_entry.setText(str(self.config.get("outdir", str(Path.cwd()))))
        self.output_name_entry.setText(str(self.config.get("output_name", "")))
        self.langs_entry.setText(str(self.config.get("langs", ",".join(DEFAULT_LANG_PRIORITY))))
        self.cookies_entry.setText(str(self.config.get("cookies_from_browser", "")))

        set_combo_value(self.format_combo, str(self.config.get("format", "txt")))
        set_combo_value(self.dedupe_combo, str(self.config.get("dedupe", "consecutive")))
        set_combo_value(self.chapter_mode_combo, str(self.config.get("chapter_mode", "none")))
        set_combo_value(self.theme_combo, str(self.config.get("theme", "oled")), fallback_index=2)

        self.timestamps_check.setChecked(bool(self.config.get("with_timestamps", True)))
        self.no_auto_check.setChecked(bool(self.config.get("no_auto", False)))
        self.no_merge_check.setChecked(bool(self.config.get("no_merge", False)))
        self.keep_vtt_check.setChecked(bool(self.config.get("keep_vtt", False)))
        self.list_subs_check.setChecked(bool(self.config.get("list_subs", False)))
        self.summary_template_check.setChecked(bool(self.config.get("summary_template", False)))
        self.quiet_check.setChecked(bool(self.config.get("quiet", False)))
        self.verbose_check.setChecked(bool(self.config.get("verbose", False)))

    def _current_mode(self) -> str:
        return "url" if self.single_url_radio.isChecked() else "file"

    def _toggle_url_file_fields(self) -> None:
        url_mode = self._current_mode() == "url"

        self.url_entry.setEnabled(url_mode)
        self.url_file_entry.setEnabled(not url_mode)
        self.url_file_browse_button.setEnabled(not url_mode)

    def browse_outdir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            self.outdir_entry.text().strip() or str(Path.cwd()),
        )

        if path:
            self.outdir_entry.setText(path)

    def browse_url_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select URL File",
            str(Path.cwd()),
            "Text Files (*.txt);;All Files (*.*)",
        )

        if path:
            self.url_file_entry.setText(path)

    def validate_form(self) -> List[str]:
        errors: List[str] = []

        mode = self._current_mode()
        url = self.url_entry.text().strip()
        url_file = self.url_file_entry.text().strip()

        if mode == "url":
            if not url:
                errors.append("URL or video ID is required.")
            if url_file:
                errors.append("URL file cannot be used in single URL mode.")
        else:
            if not url_file:
                errors.append("URL file is required for batch mode.")
            if url:
                errors.append("URL cannot be used in batch mode.")

        outdir = self.outdir_entry.text().strip()
        if not outdir:
            errors.append("Output directory is required.")

        output_name = self.output_name_entry.text().strip()
        if output_name and mode != "url":
            errors.append("Output name can only be used for single URL mode.")

        fmt = self.format_combo.currentText()
        if fmt not in OUTPUT_FORMATS:
            errors.append(f"Format must be one of: {', '.join(OUTPUT_FORMATS)}")

        dedupe = self.dedupe_combo.currentText()
        if dedupe not in ("consecutive", "consecutive-overlap", "global", "none"):
            errors.append("Deduplication mode must be one of: consecutive, consecutive-overlap, global, none")

        chapter_mode = self.chapter_mode_combo.currentText()
        if chapter_mode not in ("none", "inline", "files"):
            errors.append("Chapter mode must be one of: none, inline, files")

        return errors

    def build_options(self) -> ProcessOptions:
        langs_str = self.langs_entry.text().strip()
        langs = [lang.strip() for lang in langs_str.split(",") if lang.strip()]

        if not langs:
            langs = DEFAULT_LANG_PRIORITY[:]

        return ProcessOptions(
            langs=langs,
            outdir=Path(self.outdir_entry.text().strip()),
            output_name=self.output_name_entry.text().strip() or None,
            fmt=self.format_combo.currentText(),
            with_timestamps=self.timestamps_check.isChecked(),
            chapter_mode=self.chapter_mode_combo.currentText(),
            no_auto=self.no_auto_check.isChecked(),
            dedupe=self.dedupe_combo.currentText(),
            no_merge=self.no_merge_check.isChecked(),
            keep_vtt=self.keep_vtt_check.isChecked(),
            list_subs=self.list_subs_check.isChecked(),
            summary_template=self.summary_template_check.isChecked(),
            cookies_from_browser=self.cookies_entry.text().strip() or None,
            quiet=self.quiet_check.isChecked(),
            verbose=self.verbose_check.isChecked(),
        )

    def start(self) -> None:
        errors = self.validate_form()

        if errors:
            QMessageBox.critical(self, "Validation Error", "\n".join(errors))
            return

        self._save_config()
        self.cancel_event.clear()

        mode = self._current_mode()

        if mode == "url":
            urls = [self.url_entry.text().strip()]
        else:
            url_file = Path(self.url_file_entry.text().strip())

            try:
                with url_file.open(encoding="utf-8") as f:
                    urls = [
                        line.strip()
                        for line in f
                        if line.strip() and not line.lstrip().startswith("#")
                    ]
            except Exception as e:
                QMessageBox.critical(self, "URL File Error", f"Could not read URL file:\n\n{e}")
                return

        options = self.build_options()

        self.set_running(True)
        self.log("Starting...")

        self.worker_thread = QThread(self)
        self.worker = ProcessWorker(urls, options, self.cancel_event)
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.log.connect(self.log)
        self.worker.done.connect(self._worker_done)
        self.worker.error.connect(self._worker_error)
        self.worker.status.connect(self.statusBar().showMessage)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.finished.connect(self._thread_finished)

        self.worker_thread.start()

    def cancel(self) -> None:
        if not self.running:
            return

        self.cancel_event.set()
        self.log("Cancellation requested...")
        self.statusBar().showMessage("Cancelling...")
        self.cancel_button.setEnabled(False)

    @Slot(object)
    def _worker_done(self, result_paths: object) -> None:
        if isinstance(result_paths, list):
            for path in result_paths:
                self.log(f"Output: {path}")

        self.set_running(False)

    @Slot(str)
    def _worker_error(self, message: str) -> None:
        self.log(f"\nERROR:\n{message}")
        QMessageBox.critical(self, "Error", f"An error occurred:\n\n{message}")
        self.set_running(False)

    @Slot()
    def _thread_finished(self) -> None:
        self.worker_thread = None
        self.worker = None

        if self.running:
            self.set_running(False)

        if self.closing_after_cancel:
            self.closing_after_cancel = False
            self.close()

    def log(self, message: str) -> None:
        self.log_text.appendPlainText(message)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def set_running(self, running: bool) -> None:
        self.running = running

        self.start_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.statusBar().showMessage("Processing..." if running else "Ready")

    def open_output_folder(self) -> None:
        outdir = self.outdir_entry.text().strip()

        if not outdir:
            QMessageBox.warning(self, "Warning", "No output directory specified.")
            return

        path = Path(outdir)

        if not path.exists():
            QMessageBox.warning(self, "Warning", f"Output directory does not exist:\n{path}")
            return

        path_str = str(path)

        try:
            if platform.system() == "Windows":
                os.startfile(path_str)  # type: ignore[attr-defined]
            elif platform.system() == "Darwin":
                subprocess.run(["open", path_str], check=True)
            else:
                subprocess.run(["xdg-open", path_str], check=True)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open output folder:\n\n{e}")

    def _apply_theme(self, save: bool = True) -> None:
        theme = self.theme_combo.currentText() if hasattr(self, "theme_combo") else self.config.get("theme", "oled")

        if theme not in ("light", "dark", "oled"):
            theme = "oled"

        app = QApplication.instance()

        if app is not None:
            app.setStyle("Fusion")
            app.setStyleSheet(qss_for_theme(theme))

            try:
                from PySide6.QtGui import QGuiApplication

                scheme = Qt.ColorScheme.Light if theme == "light" else Qt.ColorScheme.Dark
                QGuiApplication.styleHints().setColorScheme(scheme)
            except Exception:
                pass

        self._apply_windows_titlebar()

        if save:
            self._save_config()

    def _apply_windows_titlebar(self) -> None:
        if platform.system() != "Windows":
            return

        try:
            import ctypes
            from ctypes import wintypes

            hwnd = int(self.winId())
            theme = self.theme_combo.currentText() if hasattr(self, "theme_combo") else "oled"
            c = THEME_COLORS.get(theme, THEME_COLORS["oled"])

            dwmapi = ctypes.WinDLL("dwmapi")

            if hasattr(wintypes, "HRESULT"):
                HRESULT = wintypes.HRESULT
            else:
                HRESULT = ctypes.c_long

            DwmSetWindowAttribute = dwmapi.DwmSetWindowAttribute
            DwmSetWindowAttribute.argtypes = [
                wintypes.HWND,
                wintypes.DWORD,
                ctypes.c_void_p,
                wintypes.DWORD,
            ]
            DwmSetWindowAttribute.restype = HRESULT

            dark_enabled = ctypes.c_int(0 if theme == "light" else 1)

            for attr in (20, 19):
                DwmSetWindowAttribute(
                    wintypes.HWND(hwnd),
                    attr,
                    ctypes.byref(dark_enabled),
                    ctypes.sizeof(dark_enabled),
                )

            def colorref(hex_color: str) -> int:
                value = hex_color.lstrip("#")
                r = int(value[0:2], 16)
                g = int(value[2:4], 16)
                b = int(value[4:6], 16)
                return r | (g << 8) | (b << 16)

            DWMWA_BORDER_COLOR = 34
            DWMWA_CAPTION_COLOR = 35
            DWMWA_TEXT_COLOR = 36

            caption = ctypes.c_int(colorref(c["titlebar"]))
            text = ctypes.c_int(colorref(c["titlebar_text"]))
            border = ctypes.c_int(colorref(c["titlebar"]))

            DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                DWMWA_CAPTION_COLOR,
                ctypes.byref(caption),
                ctypes.sizeof(caption),
            )
            DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                DWMWA_TEXT_COLOR,
                ctypes.byref(text),
                ctypes.sizeof(text),
            )
            DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                DWMWA_BORDER_COLOR,
                ctypes.byref(border),
                ctypes.sizeof(border),
            )
        except Exception as e:
            print(f"Warning: could not apply Windows title bar theme: {e}")

    def _save_config(self) -> None:
        try:
            outdir = self.outdir_entry.text().strip() if hasattr(self, "outdir_entry") else str(Path.cwd())

            if not outdir:
                outdir = str(Path.cwd())

            langs = self.langs_entry.text().strip() if hasattr(self, "langs_entry") else ",".join(DEFAULT_LANG_PRIORITY)

            if not langs:
                langs = ",".join(DEFAULT_LANG_PRIORITY)

            config = {
                "theme": self.theme_combo.currentText(),
                "dedupe": self.dedupe_combo.currentText(),
                "format": self.format_combo.currentText(),
                "with_timestamps": self.timestamps_check.isChecked(),
                "chapter_mode": self.chapter_mode_combo.currentText(),
                "no_auto": self.no_auto_check.isChecked(),
                "no_merge": self.no_merge_check.isChecked(),
                "keep_vtt": self.keep_vtt_check.isChecked(),
                "list_subs": self.list_subs_check.isChecked(),
                "summary_template": self.summary_template_check.isChecked(),
                "quiet": self.quiet_check.isChecked(),
                "verbose": self.verbose_check.isChecked(),
                "langs": langs,
                "cookies_from_browser": self.cookies_entry.text().strip(),
                "output_name": self.output_name_entry.text().strip(),
                "outdir": outdir,
            }

            with CONFIG_FILE.open("w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_config()

        if self.running:
            response = QMessageBox.question(
                self,
                "Processing is running",
                "Processing is still running. Cancel and close when it stops?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if response == QMessageBox.StandardButton.Yes:
                self.closing_after_cancel = True
                self.cancel()
                event.ignore()
            else:
                event.ignore()

            return

        event.accept()


def run_gui() -> int:
    """Run the GUI application."""
    if platform.system() == "Windows":
        os.environ.setdefault("QT_QPA_PLATFORM", "windows:darkmode=2")

    app = QApplication.instance()
    owns_app = app is None

    if app is None:
        app = QApplication(sys.argv)

    app.setApplicationName("YouTube Transcript Cleaner")
    app.setStyle("Fusion")

    window = TranscriptCleanerWindow()
    window.show()
    QTimer.singleShot(0, window._apply_windows_titlebar)

    if owns_app:
        return int(app.exec())

    return 0
