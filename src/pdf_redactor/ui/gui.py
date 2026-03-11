import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox, 
    QListWidget, QFileDialog, QProgressBar, QMessageBox, QGroupBox,
    QTabWidget, QFormLayout
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon

from pdf_redactor.config.settings_manager import SettingsManager
from pdf_redactor.utils.file_manager import FileManager
from pdf_redactor.core.pdf_parser import PDFParser
from pdf_redactor.core.ocr_engine import OCREngine
from pdf_redactor.core.redaction_engine import RedactionEngine
from pdf_redactor.core.redaction_styles import RedactionMode

class DropListWidget(QListWidget):
    """A list widget that accepts PDF file drops."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith('.pdf'):
                items = [self.item(i).text() for i in range(self.count())]
                if file_path not in items:
                    self.addItem(file_path)

class WorkerThread(QThread):
    """Runs the redaction batch process in the background."""
    progress = Signal(int)
    log = Signal(str)
    error = Signal(str)
    finished_batch = Signal()

    def __init__(self, files, phrases, mode, out_dir, use_ocr, case_sensitive, ocr_lang, generate_audit):
        super().__init__()
        self.files = files
        self.phrases = phrases
        self.mode = mode
        self.out_dir = out_dir
        self.use_ocr = use_ocr
        self.case_sensitive = case_sensitive
        self.ocr_lang = ocr_lang
        self.generate_audit = generate_audit

    def run(self):
        total = len(self.files)
        for idx, pdf_path in enumerate(self.files):
            self.log.emit(f"Processing: {os.path.basename(pdf_path)}")
            try:
                pdf_parser = PDFParser(pdf_path)
                all_matches = {}
                audit_data = []
                pages_needing_ocr = []
                pages_text_status = pdf_parser.get_all_pages_text_status()
                
                for page_num, has_text in pages_text_status.items():
                    if self.use_ocr or not has_text:
                        pages_needing_ocr.append(page_num)
                        
                pages_with_text = [p for p, has_text in pages_text_status.items() if has_text and not self.use_ocr]
                
                if pages_with_text:
                    text_matches = pdf_parser.find_phrases(self.phrases, self.case_sensitive)
                    for page_num, matches in text_matches.items():
                        if page_num in pages_with_text:
                            all_matches.setdefault(page_num, []).extend([m[1] for m in matches])
                            for phrase, rect in matches:
                                audit_data.append({'file': os.path.basename(pdf_path), 'page': page_num + 1, 'phrase': phrase, 'type': 'Text'})

                pdf_parser.close()
                
                if pages_needing_ocr:
                    try:
                        self.log.emit("Starting OCR Engine (Multi-threaded)...")
                        ocr_engine = OCREngine(pdf_path)
                        
                        def ocr_progress(current, total_ocr):
                            self.log.emit(f"OCR: Completed {current} of {total_ocr} pages...")
                            # Calculate overall progress incorporating the partial file completion
                            base_prog = (idx / total) * 100
                            file_prog = (current / total_ocr) * (100 / total)
                            self.progress.emit(int(base_prog + file_prog))
                        ocr_matches = ocr_engine.find_phrases(
                            self.phrases, 
                            self.case_sensitive, 
                            target_pages=pages_needing_ocr,
                            progress_callback=ocr_progress,
                            lang=self.ocr_lang
                        )
                        for page_num, matches in ocr_matches.items():
                            all_matches.setdefault(page_num, []).extend([m[1] for m in matches])
                            for phrase, rect in matches:
                                audit_data.append({'file': os.path.basename(pdf_path), 'page': page_num + 1, 'phrase': phrase, 'type': 'OCR'})
                    except Exception as eval_err:
                        self.error.emit(f"OCR Failed on {os.path.basename(pdf_path)}: {eval_err}")

                if any(all_matches.values()):
                    self.log.emit("Applying true redactions & wiping metadata...")
                    engine = RedactionEngine(pdf_path)
                    engine.apply_redactions(all_matches, self.mode)
                    out_path = FileManager.prepare_output_path(pdf_path, self.out_dir)
                    engine.save(out_path)
                    engine.close()
                    
                    if self.generate_audit and audit_data:
                        try:
                            import csv
                            from datetime import datetime
                            audit_path = os.path.join(self.out_dir, "redaction_audit_log.csv")
                            file_exists = os.path.isfile(audit_path)
                            with open(audit_path, mode='a', newline='', encoding='utf-8') as f:
                                writer = csv.writer(f)
                                if not file_exists:
                                    writer.writerow(["Timestamp", "File Name", "Page Number", "Redacted Phrase", "Detection Method"])
                                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                for item in audit_data:
                                    writer.writerow([timestamp, item['file'], item['page'], item['phrase'], item['type']])
                            self.log.emit(f"Saved PDF and updated Audit Log.")
                        except Exception as e:
                            self.error.emit(f"Failed to write audit log: {str(e)}")
                    else:
                        self.log.emit(f"Saved: {os.path.basename(out_path)}")
                else:
                    self.log.emit(f"No phrases matched in {os.path.basename(pdf_path)}. Skipped.")
            except Exception as e:
                self.error.emit(f"Failed to process {os.path.basename(pdf_path)}: {str(e)}")
            
            self.progress.emit(int(((idx + 1) / total) * 100))

        self.finished_batch.emit()

from pdf_redactor.utils.resource_handler import get_resource_path

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = SettingsManager()
        self.setWindowTitle("Blnq")
        
        icon_path = get_resource_path(os.path.join("resources", "icons", "app_icon.png"))
            
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.resize(650, 500)
        self._init_ui()

    def _init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.tab_workspace = QWidget()
        self.tabs.addTab(self.tab_workspace, "Workspace")
        self._init_workspace_tab()

        self.tab_settings = QWidget()
        self.tabs.addTab(self.tab_settings, "Settings")
        self._init_settings_tab()
        
        self.tab_audit = QWidget()
        self.tabs.addTab(self.tab_audit, "Audit & Logging")
        self._init_audit_tab()

        self.label_status = QLabel("Ready")
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        
        self.btn_process = QPushButton("Process PDFs")
        self.btn_process.setMinimumHeight(40)
        self.btn_process.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.btn_process.clicked.connect(self.start_processing)

        layout.addWidget(self.label_status)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.btn_process)

    def _init_workspace_tab(self):
        layout = QVBoxLayout(self.tab_workspace)
        
        group_input = QGroupBox("Input PDFs")
        v_input = QVBoxLayout(group_input)
        self.list_files = DropListWidget()
        v_input.addWidget(QLabel("Drag and drop PDF files below:"))
        v_input.addWidget(self.list_files)
        
        btn_layout = QHBoxLayout()
        self.btn_add_files = QPushButton("Add Files")
        self.btn_add_files.clicked.connect(self.browse_files)
        self.btn_clear_files = QPushButton("Clear")
        self.btn_clear_files.clicked.connect(self.list_files.clear)
        btn_layout.addWidget(self.btn_add_files)
        btn_layout.addWidget(self.btn_clear_files)
        v_input.addLayout(btn_layout)
        layout.addWidget(group_input)

        group_phrases = QGroupBox("Target Phrases")
        v_phrases = QVBoxLayout(group_phrases)
        v_phrases.addWidget(QLabel("Phrases to redact (comma separated):"))
        self.input_phrase = QLineEdit()
        self.input_phrase.setPlaceholderText("e.g. John Doe, Confidential, 555-0100")
        v_phrases.addWidget(self.input_phrase)
        layout.addWidget(group_phrases)

    def _init_settings_tab(self):
        layout = QFormLayout(self.tab_settings)

        self.combo_mode = QComboBox()
        self.combo_mode.addItem("Black Bar (True Redact)", RedactionMode.BLACK_BAR)
        self.combo_mode.addItem("Red Box Outline", RedactionMode.RED_BOX)
        self.combo_mode.addItem("Yellow Highlight", RedactionMode.HIGHLIGHT)
        
        saved_mode = self.settings.get("default_mode")
        for i in range(self.combo_mode.count()):
            if self.combo_mode.itemData(i).value == saved_mode:
                self.combo_mode.setCurrentIndex(i)
                break
        layout.addRow("Redaction Style:", self.combo_mode)

        self.combo_lang = QComboBox()
        self.combo_lang.addItem("English", "eng")
        self.combo_lang.addItem("Romanian", "ron")
        self.combo_lang.addItem("Russian", "rus")
        
        saved_lang = self.settings.get("ocr_language")
        for i in range(self.combo_lang.count()):
            if self.combo_lang.itemData(i) == saved_lang:
                self.combo_lang.setCurrentIndex(i)
                break
        layout.addRow("OCR Language:", self.combo_lang)

        h_out = QHBoxLayout()
        self.input_out_dir = QLineEdit()
        self.input_out_dir.setText(self.settings.get("output_directory"))
        self.btn_browse_out = QPushButton("Browse...")
        self.btn_browse_out.clicked.connect(self.browse_out_dir)
        h_out.addWidget(self.input_out_dir)
        h_out.addWidget(self.btn_browse_out)
        layout.addRow("Output Directory:", h_out)

        self.check_ocr = QCheckBox("Force OCR mode (for scanned PDFs)")
        self.check_ocr.setChecked(self.settings.get("ocr_enabled"))
        layout.addRow("", self.check_ocr)

        self.check_case = QCheckBox("Case Sensitive Matching")
        self.check_case.setChecked(self.settings.get("case_sensitive"))
        layout.addRow("", self.check_case)

    def _init_audit_tab(self):
        layout = QVBoxLayout(self.tab_audit)
        
        group_audit = QGroupBox("Forensic Audit Logging")
        v_audit = QVBoxLayout(group_audit)
        
        self.check_audit = QCheckBox("Generate CSV Audit Log in Output Directory")
        self.check_audit.setChecked(self.settings.get("generate_audit"))
        v_audit.addWidget(self.check_audit)
        
        desc = QLabel("If enabled, a 'redaction_audit_log.csv' will be generated alongside the redacted PDFs. \nThis file logs the exact timestamp, file name, page number, underlying phrase, \nand detection method (Text vs OCR) for every single applied redaction block to satisfy \ncompliance and tracking requirements.")
        desc.setWordWrap(True)
        v_audit.addWidget(desc)
        
        v_audit.addStretch()
        layout.addWidget(group_audit)

    def browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select PDFs", "", "PDF Files (*.pdf)")
        if files:
            current_items = [self.list_files.item(i).text() for i in range(self.list_files.count())]
            for f in files:
                if f not in current_items:
                    self.list_files.addItem(f)

    def browse_out_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if folder:
            self.input_out_dir.setText(folder)

    def save_settings(self):
        self.settings.set("ocr_enabled", self.check_ocr.isChecked())
        self.settings.set("case_sensitive", self.check_case.isChecked())
        self.settings.set("default_mode", self.combo_mode.currentData().value)
        self.settings.set("output_directory", self.input_out_dir.text())
        self.settings.set("ocr_language", self.combo_lang.currentData())
        self.settings.set("generate_audit", self.check_audit.isChecked())
        self.settings.save()

    def start_processing(self):
        files = [self.list_files.item(i).text() for i in range(self.list_files.count())]
        if not files:
            QMessageBox.warning(self, "Error", "Please add at least one PDF file.")
            return

        phrases_text = self.input_phrase.text().strip()
        if not phrases_text:
            QMessageBox.warning(self, "Error", "Please enter at least one phrase to redact.")
            return

        phrases = [p.strip() for p in phrases_text.split(",") if p.strip()]

        out_dir = self.input_out_dir.text().strip()
        if not out_dir:
            QMessageBox.warning(self, "Error", "Please specify an output directory in Settings.")
            self.tabs.setCurrentIndex(1)
            return

        self.save_settings()

        self.btn_process.setEnabled(False)
        self.progress_bar.setValue(0)
        self.label_status.setText("Processing started...")

        self.worker = WorkerThread(
            files=files,
            phrases=phrases,
            mode=self.combo_mode.currentData(),
            out_dir=out_dir,
            use_ocr=self.check_ocr.isChecked(),
            case_sensitive=self.check_case.isChecked(),
            ocr_lang=self.combo_lang.currentData(),
            generate_audit=self.check_audit.isChecked()
        )
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.log.connect(self.label_status.setText)
        self.worker.error.connect(lambda msg: QMessageBox.critical(self, "Error", msg))
        self.worker.finished_batch.connect(self.processing_finished)
        self.worker.start()

    def processing_finished(self):
        self.btn_process.setEnabled(True)
        self.label_status.setText("Processing finished successfully.")

def run_gui():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
