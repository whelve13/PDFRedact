import sys
import os
import copy
import fitz
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox, 
    QListWidget, QFileDialog, QProgressBar, QMessageBox, QGroupBox,
    QTabWidget, QFormLayout, QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsPixmapItem
)
from PySide6.QtCore import Qt, QThread, Signal, QRectF
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QPixmap, QImage, QPainter, QPen, QColor, QBrush

from pdf_redactor.config.settings_manager import SettingsManager
from pdf_redactor.utils.file_manager import FileManager
from pdf_redactor.core.pdf_parser import PDFParser
from pdf_redactor.core.ocr_engine import OCREngine
from pdf_redactor.core.redaction_engine import RedactionEngine
from pdf_redactor.core.redaction_styles import RedactionMode
from pdf_redactor.utils.resource_handler import get_resource_path

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

class InteractiveGraphicsView(QGraphicsView):
    """A Graphics View enabling interactive dragging and deleting of redaction boxes."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setDragMode(QGraphicsView.NoDrag)
        self.zoom = 2.0
        
        self.drawing = False
        self.start_pos = None
        self.current_rect_item = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Check if clicked on an existing box
            item = self.itemAt(event.pos())
            if isinstance(item, QGraphicsRectItem):
                self.scene.removeItem(item)
                return
            
            # Start drawing a new manual redaction box
            self.drawing = True
            pos = self.mapToScene(event.pos())
            self.start_pos = pos
            self.current_rect_item = QGraphicsRectItem()
            pen = QPen(QColor(255, 0, 0))
            pen.setWidth(2)
            self.current_rect_item.setPen(pen)
            self.current_rect_item.setBrush(QBrush(QColor(255, 0, 0, 80)))
            self.scene.addItem(self.current_rect_item)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drawing and self.current_rect_item:
            end_pos = self.mapToScene(event.pos())
            rect = QRectF(self.start_pos, end_pos).normalized()
            self.current_rect_item.setRect(rect)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.drawing:
            self.drawing = False
            if self.current_rect_item:
                if self.current_rect_item.rect().width() < 5 or self.current_rect_item.rect().height() < 5:
                    self.scene.removeItem(self.current_rect_item)
            self.current_rect_item = None
        super().mouseReleaseEvent(event)
        
    def load_page(self, img_bytes, rect_tuples, display_mat):
        self.scene.clear()
        
        # Load high-res background PDF layer
        pixmap = QPixmap()
        pixmap.loadFromData(img_bytes, "PNG")
        bg_item = QGraphicsPixmapItem(pixmap)
        bg_item.setZValue(0) # Bottom
        self.scene.addItem(bg_item)
        self.scene.setSceneRect(bg_item.boundingRect())
        
        # Overlay existing matched bounding boxes
        for r_tuple in rect_tuples:
            # Map PDF points (tuples) back to pixels using display_mat
            rect = fitz.Rect(r_tuple)
            scaled_rect = rect * display_mat
            
            box_qrect = QRectF(scaled_rect.x0, scaled_rect.y0, 
                               scaled_rect.width, scaled_rect.height)
            
            box = QGraphicsRectItem(box_qrect)
            box.setPen(QPen(QColor(255, 0, 0, 200), 2))
            box.setBrush(QBrush(QColor(255, 0, 0, 60)))
            box.setZValue(1) # Top
            self.scene.addItem(box)
            
    def get_user_approved_rects(self, display_mat):
        """Extract all QGraphicsRectItems back into PyMuPDF coordinate space via inverse matrix."""
        inv_mat = ~display_mat
        approved = []
        for item in self.scene.items():
            if isinstance(item, QGraphicsRectItem):
                qrect = item.rect()
                # UI points -> PDF points
                pixel_rect = fitz.Rect(qrect.x(), qrect.y(), qrect.x() + qrect.width(), qrect.y() + qrect.height())
                pdf_rect = pixel_rect * inv_mat
                approved.append((pdf_rect.x0, pdf_rect.y0, pdf_rect.x1, pdf_rect.y1))
        return approved

class AnalysisWorker(QThread):
    progress = Signal(int)
    log = Signal(str)
    error = Signal(str)
    finished_file_analysis = Signal(str, object, list, int) # path, matches, audit, total_pages
    finished_batch = Signal()

    def __init__(self, files, phrases, use_ocr, case_sensitive, ocr_lang):
        super().__init__()
        self.files = files
        self.phrases = phrases
        self.use_ocr = use_ocr
        self.case_sensitive = case_sensitive
        self.ocr_lang = ocr_lang

    def run(self):
        total = len(self.files)
        for idx, pdf_path in enumerate(self.files):
            self.log.emit(f"Analyzing: {os.path.basename(pdf_path)}")
            try:
                pdf_parser = PDFParser(pdf_path)
                total_pages = len(pdf_parser.doc)
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
                                audit_data.append({
                                    'file': os.path.basename(pdf_path), 
                                    'page': page_num + 1, 
                                    'phrase': phrase, 
                                    'type': 'Text',
                                    'rect': (rect.x0, rect.y0, rect.x1, rect.y1)
                                })

                pdf_parser.close()
                
                if pages_needing_ocr:
                    try:
                        self.log.emit("Starting OCR Engine (Multi-threaded)...")
                        ocr_engine = OCREngine(pdf_path)
                        
                        def ocr_progress(current, total_ocr):
                            self.log.emit(f"OCR: Completed {current} of {total_ocr} pages...")
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
                                audit_data.append({
                                    'file': os.path.basename(pdf_path), 
                                    'page': page_num + 1, 
                                    'phrase': phrase, 
                                    'type': 'OCR',
                                    'rect': (rect.x0, rect.y0, rect.x1, rect.y1)
                                })
                    except Exception as eval_err:
                        self.error.emit(f"OCR Failed on {os.path.basename(pdf_path)}: {eval_err}")

                self.progress.emit(int(((idx + 0.5) / total) * 100))
                
                # Deduplicate and standardize matches (convert fitz.Rect to tuples for signal safety)
                serialized_matches = {}
                for p_num, p_rects in all_matches.items():
                    # Deduplicate overlapping boxes (especially if Text and OCR both found the same word)
                    unique_rects = []
                    for r in p_rects:
                        is_duplicate = False
                        for u in unique_rects:
                            # If boxes overlap significantly (>80%), consider them duplicates
                            if r.intersects(u):
                                intersect_area = r.intersect(u).get_area()
                                if intersect_area > 0.8 * r.get_area() or intersect_area > 0.8 * u.get_area():
                                    is_duplicate = True
                                    # Keep the larger one
                                    if r.get_area() > u.get_area():
                                        unique_rects.remove(u)
                                        unique_rects.append(r)
                                    break
                        if not is_duplicate:
                            unique_rects.append(r)
                            
                    serialized_matches[p_num] = [(r.x0, r.y0, r.x1, r.y1) for r in unique_rects]

                self.finished_file_analysis.emit(pdf_path, serialized_matches, audit_data, total_pages)
            except Exception as e:
                self.error.emit(f"Failed to analyze {os.path.basename(pdf_path)}: {str(e)}")
                import traceback
                traceback.print_exc()
            
            self.progress.emit(int(((idx + 1) / total) * 100))

        self.finished_batch.emit()

class ExecutionWorker(QThread):
    progress = Signal(int)
    log = Signal(str)
    error = Signal(str)
    finished_execution = Signal()

    def __init__(self, pending_tasks, mode, out_dir, generate_audit):
        """pending_tasks: dict matching filepath -> {'matches': Dict[int, List], 'audit': List}"""
        super().__init__()
        self.pending_tasks = pending_tasks
        self.mode = mode
        self.out_dir = out_dir
        self.generate_audit = generate_audit
        
    def run(self):
        total = len(self.pending_tasks.keys())
        for idx, (pdf_path, task) in enumerate(self.pending_tasks.items()):
            all_matches = task['matches']
            audit_data = task['audit']
            
            try:
                if any(all_matches.values()):
                    self.log.emit(f"Applying true redactions to {os.path.basename(pdf_path)} ...")
                    engine = RedactionEngine(pdf_path)
                    engine.apply_redactions(all_matches, self.mode)
                    out_path = FileManager.prepare_output_path(pdf_path, self.out_dir)
                    engine.save(out_path)
                    engine.close()
                    
                    if self.generate_audit:
                        try:
                            import csv
                            import fitz
                            from datetime import datetime
                            audit_path = os.path.join(self.out_dir, "redaction_audit_log.csv")
                            file_exists = os.path.isfile(audit_path)
                            with open(audit_path, mode='a', newline='', encoding='utf-8') as f:
                                writer = csv.writer(f)
                                if not file_exists:
                                    writer.writerow(["Timestamp", "File Name", "Page Number", "Redacted Phrase", "Detection Method"])
                                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                
                                for page_num, rect_tuples in all_matches.items():
                                    for rect in rect_tuples:
                                        matched_phrase = "Manual Redaction"
                                        det_type = "Manual"
                                        app_rect = fitz.Rect(rect)
                                        
                                        for item in audit_data:
                                            if item['page'] == page_num + 1 and 'rect' in item:
                                                audit_rect = fitz.Rect(item['rect'])
                                                if audit_rect.intersects(app_rect):
                                                    intersect_area = audit_rect.intersect(app_rect).get_area()
                                                    if intersect_area > 0.8 * app_rect.get_area() or intersect_area > 0.8 * audit_rect.get_area():
                                                        matched_phrase = item['phrase']
                                                        det_type = item['type']
                                                        break
                                        
                                        writer.writerow([timestamp, os.path.basename(pdf_path), page_num + 1, matched_phrase, det_type])
                            self.log.emit(f"Saved PDF and updated Audit Log.")
                        except Exception as e:
                            self.error.emit(f"Failed to write audit log: {str(e)}")
                    else:
                        self.log.emit(f"Saved: {os.path.basename(out_path)}")
                else:
                    self.log.emit(f"No boxes selected for {os.path.basename(pdf_path)}. Skipped.")
            except Exception as e:
                self.error.emit(f"Failed execution for {os.path.basename(pdf_path)}: {str(e)}")
            
            self.progress.emit(int(((idx + 1) / total) * 100))
            
        self.finished_execution.emit()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = SettingsManager()
        self.setWindowTitle("Blnq")
        
        icon_path = get_resource_path(os.path.join("resources", "icons", "app_icon.ico"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.resize(1000, 750)
        self.analyzed_data = {} # Maps file_path -> {"matches": {...}, "audit": [...], "total_pages": int}
        self.current_preview_page = 0
        
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
        
        self.tab_preview = QWidget()
        self.tabs.addTab(self.tab_preview, "Preview && Apply")
        self._init_preview_tab()
        self.tab_preview.setEnabled(False) # Unlock after analysis

        self.tab_settings = QWidget()
        self.tabs.addTab(self.tab_settings, "Settings")
        self._init_settings_tab()
        
        self.tab_audit = QWidget()
        self.tabs.addTab(self.tab_audit, "Audit && Logging")
        self._init_audit_tab()

        self.label_status = QLabel("Ready")
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        
        layout.addWidget(self.label_status)
        layout.addWidget(self.progress_bar)

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
        
        self.btn_analyze = QPushButton("Analyze Documents")
        self.btn_analyze.setMinimumHeight(40)
        self.btn_analyze.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.btn_analyze.clicked.connect(self.start_analysis)
        layout.addWidget(self.btn_analyze)

    def _init_preview_tab(self):
        layout = QVBoxLayout(self.tab_preview)
        
        h_ctrl = QHBoxLayout()
        h_ctrl.addWidget(QLabel("Viewing File:"))
        self.combo_preview_file = QComboBox()
        self.combo_preview_file.currentIndexChanged.connect(self.on_preview_file_changed)
        self.btn_clear_preview = QPushButton("Clear Preview")
        self.btn_clear_preview.clicked.connect(self.clear_preview)
        h_ctrl.addWidget(self.combo_preview_file, stretch=1)
        h_ctrl.addWidget(self.btn_clear_preview)
        
        self.btn_zoom_in = QPushButton("Zoom In")
        self.btn_zoom_out = QPushButton("Zoom Out")
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        h_ctrl.addWidget(self.btn_zoom_in)
        h_ctrl.addWidget(self.btn_zoom_out)
        
        layout.addLayout(h_ctrl)
        
        self.graphics_view = InteractiveGraphicsView()
        layout.addWidget(self.graphics_view)
        
        h_page_ctrl = QHBoxLayout()
        self.btn_prev_page = QPushButton("<< Previous Page")
        self.btn_prev_page.clicked.connect(self.prev_preview_page)
        
        self.label_preview_status = QLabel("Page 0 / 0")
        self.label_preview_status.setAlignment(Qt.AlignCenter)
        
        self.btn_next_page = QPushButton("Next Page >>")
        self.btn_next_page.clicked.connect(self.next_preview_page)
        
        h_page_ctrl.addWidget(self.btn_prev_page)
        h_page_ctrl.addWidget(self.label_preview_status, stretch=1)
        h_page_ctrl.addWidget(self.btn_next_page)
        layout.addLayout(h_page_ctrl)
        
        self.btn_execute = QPushButton("Commit Approved Redactions")
        self.btn_execute.setMinimumHeight(40)
        self.btn_execute.setStyleSheet("font-weight: bold; font-size: 14px; background-color: #aa0000; color: white;")
        self.btn_execute.clicked.connect(self.start_execution)
        layout.addWidget(self.btn_execute)

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

        self.check_open_out = QCheckBox("Open output folder after completion")
        # Default to True by checking if the setting explicitly equals False
        self.check_open_out.setChecked(self.settings.get("open_output_folder") is not False)
        layout.addRow("", self.check_open_out)

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
        self.settings.set("open_output_folder", self.check_open_out.isChecked())
        self.settings.save()

    def _show_error(self, msg):
        """Thread-safe error handler — Qt auto-queues since this is a QObject method."""
        QMessageBox.critical(self, "Error", msg)

    def start_analysis(self):
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
            self.tabs.setCurrentIndex(2)
            return

        self.save_settings()

        self.btn_analyze.setEnabled(False)
        self.progress_bar.setValue(0)
        self.label_status.setText("Analysis started...")
        self.analyzed_data.clear()
        self.graphics_view.scene.clear()  # Wipe old preview so stale boxes don't leak into new results
        self.combo_preview_file.clear()

        self.worker = AnalysisWorker(
            files=files,
            phrases=phrases,
            use_ocr=self.check_ocr.isChecked(),
            case_sensitive=self.check_case.isChecked(),
            ocr_lang=self.combo_lang.currentData()
        )
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.log.connect(self.label_status.setText)
        self.worker.error.connect(self._show_error)
        self.worker.finished_file_analysis.connect(self.on_file_analyzed)
        self.worker.finished_batch.connect(self.analysis_finished)
        self.worker.start()

    def on_file_analyzed(self, path, matches, audit, total_pages):
        self.analyzed_data[path] = {
            "matches": matches,
            "audit": audit,
            "total_pages": total_pages
        }
        self.combo_preview_file.addItem(os.path.basename(path), path)

    def analysis_finished(self):
        self.btn_analyze.setEnabled(True)
        self.label_status.setText("Analysis finished! Proceed to the Preview & Apply tab.")
        self.tab_preview.setEnabled(True)
        self.tabs.setCurrentIndex(1) # Snap to Preview App
        if self.combo_preview_file.count() > 0:
            self.combo_preview_file.setCurrentIndex(0)

    # --- PREVIEW ENGINE ---

    def on_preview_file_changed(self, index):
        if index < 0:
            return
        self.save_current_preview_page()
        self.current_preview_page = 0
        self.load_preview_page()

    def save_current_preview_page(self):
        file_path = self.combo_preview_file.currentData()
        if not file_path or file_path not in self.analyzed_data:
            return
        
        # Guard: only save if a page has actually been rendered.
        # Without this, the initial combo population triggers on_preview_file_changed
        # before any page is drawn, causing get_user_approved_rects() to return []
        # and wipe the original analysis matches for page 0.
        has_rendered_page = any(
            isinstance(item, QGraphicsPixmapItem) for item in self.graphics_view.scene.items()
        )
        if not has_rendered_page:
            return
            
        page_num = self.current_preview_page
        
        # Zoom-only matrix: get_pixmap already handles page rotation internally,
        # so display_mat must match — just the zoom, no extra rotation_matrix.
        display_mat = fitz.Matrix(self.graphics_view.zoom, self.graphics_view.zoom)
        
        user_approved = self.graphics_view.get_user_approved_rects(display_mat)
        self.analyzed_data[file_path]["matches"][page_num] = user_approved

    def load_preview_page(self):
        file_path = self.combo_preview_file.currentData()
        if not file_path or file_path not in self.analyzed_data:
            return
            
        page_num = self.current_preview_page
        
        try:
            # Fast Engine Load for pure visual extraction
            engine = RedactionEngine(file_path)
            img_bytes = engine.get_page_image(page_num, zoom=self.graphics_view.zoom)
            engine.close()
            
            # Zoom-only matrix: get_pixmap already handles page rotation internally
            display_mat = fitz.Matrix(self.graphics_view.zoom, self.graphics_view.zoom)
            
            matches = self.analyzed_data[file_path]["matches"].get(page_num, [])
            
            self.graphics_view.load_page(img_bytes, matches, display_mat)
            self.label_preview_status.setText(f"Page {page_num + 1} / {self.analyzed_data[file_path]['total_pages']}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "Preview Error", f"Unable to load page view: {str(e)}")

    def prev_preview_page(self):
        file_path = self.combo_preview_file.currentData()
        if not file_path or file_path not in self.analyzed_data:
            return
        if self.current_preview_page > 0:
            self.save_current_preview_page()
            self.current_preview_page -= 1
            self.load_preview_page()

    def next_preview_page(self):
        file_path = self.combo_preview_file.currentData()
        if not file_path or file_path not in self.analyzed_data:
            return
        total = self.analyzed_data[file_path]["total_pages"]
        if self.current_preview_page < total - 1:
            self.save_current_preview_page()
            self.current_preview_page += 1
            self.load_preview_page()

    def clear_preview(self):
        self.graphics_view.scene.clear()
        self.combo_preview_file.clear()
        self.label_preview_status.setText("Page 0 / 0")
        self.analyzed_data.clear()

    def zoom_in(self):
        if self.combo_preview_file.count() > 0:
            self.save_current_preview_page()  # Save with CURRENT zoom before changing
            self.graphics_view.zoom += 0.5
            self.load_preview_page()
            
            # Lock the view onto the exact center of the generated PDF page Pixmap
            self.graphics_view.centerOn(self.graphics_view.scene.sceneRect().center())

    def zoom_out(self):
        if self.combo_preview_file.count() > 0 and self.graphics_view.zoom > 1.0:
            self.save_current_preview_page()  # Save with CURRENT zoom before changing
            self.graphics_view.zoom -= 0.5
            self.load_preview_page()
            
            # Lock the view onto the exact center of the generated PDF page Pixmap
            self.graphics_view.centerOn(self.graphics_view.scene.sceneRect().center())

    # --- FINAL EXECUTION ---
    
    def start_execution(self):
        self.save_current_preview_page() # Ensure the currently visible page's boxes are saved!
        
        # Verify that we actually have any boxes to execute
        total_boxes = sum(len(boxes) for req in self.analyzed_data.values() for boxes in req['matches'].values())
        if total_boxes == 0:
            QMessageBox.information(self, "Warning", "You have zero redaction boxes drawn across all documents.")
            return
            
        self.btn_execute.setEnabled(False)
        self.tab_preview.setEnabled(False)
        self.progress_bar.setValue(0)
        self.label_status.setText("Applying permanent redactions...")
        
        self.worker = ExecutionWorker(
            pending_tasks=copy.deepcopy(self.analyzed_data),
            mode=self.combo_mode.currentData(),
            out_dir=self.input_out_dir.text().strip(),
            generate_audit=self.check_audit.isChecked()
        )
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.log.connect(self.label_status.setText)
        self.worker.error.connect(self._show_error)
        self.worker.finished_execution.connect(self.execution_finished)
        self.worker.start()

    def execution_finished(self):
        self.btn_execute.setEnabled(True)
        self.tab_preview.setEnabled(True)
        self.label_status.setText("All documents saved successfully!")
        QMessageBox.information(self, "Success", "All processed documents have been saved dynamically to your output folder.")
        
        if self.check_open_out.isChecked():
            out_dir = self.input_out_dir.text().strip()
            if os.path.exists(out_dir):
                os.startfile(out_dir)

def run_gui():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
