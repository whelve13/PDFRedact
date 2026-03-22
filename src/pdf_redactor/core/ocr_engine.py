import fitz
from PIL import Image
import pytesseract
from pytesseract import Output
import os
import sys
from typing import List, Dict

from pathlib import Path

def get_tesseract_paths():
    """
    Robustly locate the tesseract binaries depending on whether the app is:
    1. A packaged Pyinstaller executable (checking bundled _MEIPASS or placed next to executable)
    2. A standard python development environment
    """
    possible_base_paths = []
    
    if getattr(sys, 'frozen', False):
        # We are running as a PyInstaller bundle
        # 1. First check if tesseract_bin is BUNDLED INSIDE the bundle (_MEIPASS temp dir)
        if hasattr(sys, '_MEIPASS'):
            possible_base_paths.append(Path(sys._MEIPASS))
        
        # 2. Then check if tesseract_bin is placed NEXT to the executable (e.g., by Inno Setup)
        possible_base_paths.append(Path(sys.executable).parent)
    else:
        # 3. We are running in a normal Python environment
        # project_root/src/pdf_redactor/core/ocr_engine.py
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        possible_base_paths.append(project_root)

    for base in possible_base_paths:
        t_path = base / 'tesseract_bin' / 'tesseract.exe'
        t_data = base / 'tesseract_bin' / 'tessdata'
        
        if t_path.exists() and t_data.exists():
            # Convert to absolute strings with forward slashes to prevent Windows escape bugs in PyTesseract subprocesses
            return str(t_path.resolve()).replace('\\', '/'), str(t_data.resolve()).replace('\\', '/')
            
    # Fallback if not found anywhere
    return None, None

tess_path, tessdata_path = get_tesseract_paths()

if tess_path and tessdata_path:
    pytesseract.pytesseract.tesseract_cmd = tess_path
    os.environ["TESSDATA_PREFIX"] = tessdata_path
else:
    # Fallback to system PATH if not bundled
    tessdata_path = ""

class OCREngine:
    """
    Handles scanned PDFs using Tesseract OCR to find phrase bounding boxes.
    """
    def __init__(self, pdf_path: str, dpi: int = 300):
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        self.pdf_path = pdf_path
        self.dpi = dpi

    def find_phrases(self, phrases: List[str], case_sensitive: bool = False, target_pages: List[int] = None, progress_callback=None, lang="eng") -> Dict[int, List[tuple]]:
        """
        Runs OCR on given pages concurrently and returns bounding boxes of found phrases.
        Uses a fixed multi-threading pool to accelerate scanning without out-of-memory errors by keeping 
        only active worker images in RAM.
        Returns:
            A dictionary mapping page_num -> list of (phrase_matched, fitz.Rect)
        """
        import concurrent.futures
        matches = {}
        
        # Get total pages fast
        temp_doc = fitz.open(self.pdf_path)
        total_pages = len(temp_doc)
        temp_doc.close()
        
        pages_to_process = target_pages if target_pages is not None else list(range(total_pages))
        
        scale_factor = 72.0 / self.dpi
        zoom = self.dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        
        def _process_page(page_num):
            import cv2
            import numpy as np
            
            # Isolated PDF instance per thread for thread safety
            local_doc = fitz.open(self.pdf_path)
            page = local_doc[page_num]
            
            # Inverse of the rendering matrix maps OCR pixels -> PDF points.
            # No rotation_matrix needed: get_pixmap already handles page rotation.
            inv_mat = ~mat
            
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            pix = None  # Release C-level pixmap buffer immediately
            local_doc.close()
            
            # --- OpenCV Preprocessing Pipeline ---
            open_cv_image = np.array(img)
            open_cv_image = open_cv_image[:, :, ::-1].copy()  # RGB -> BGR for OpenCV
                
            gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)
            denoised = cv2.fastNlMeansDenoising(gray, h=10)
            
            # --- Morphological Underline Removal ---
            # Create an inverted binary image (text/lines white, background black)
            _, img_bin_inv = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            
            # Detect horizontal lines
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
            horizontal_lines = cv2.morphologyEx(img_bin_inv, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)
            
            # Subtract lines and revert to standard binary (black text, white bg)
            text_only_inv = cv2.subtract(img_bin_inv, horizontal_lines)
            binary = cv2.bitwise_not(text_only_inv)
            
            page_matches = []
            
            # Apply PSM 6 config for pipeline efficiency and explicitly point to the dynamic tessdata folder
            custom_config = f'--tessdata-dir {tessdata_path} --psm 6' if tessdata_path else '--psm 6'
            data = pytesseract.image_to_data(binary, lang=lang, config=custom_config, output_type=Output.DICT)
            
            # Logical Line grouping
            lines = {}
            for i in range(len(data['text'])):
                word_text = data['text'][i].strip()
                # Increase confidence threshold to 50 to reduce false positives
                if int(data['conf'][i]) >= 50 and word_text:
                    key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
                    if key not in lines:
                        lines[key] = []
                    lines[key].append({
                        'text': word_text,
                        'rect': fitz.Rect(data['left'][i], data['top'][i], 
                                          data['left'][i] + data['width'][i], 
                                          data['top'][i] + data['height'][i]),
                    })
            
            for key, words in lines.items():
                # Continuous mapping covering space-divided font clusters
                compressed_line = []
                char_to_word_idx = []
                
                for w_idx, w in enumerate(words):
                    text = w['text']
                    compressed_line.append(text)
                    # Create dictionary indexing where each character belongs back to which word coordinate
                    char_to_word_idx.extend([w_idx] * len(text))
                
                line_flat = "".join(compressed_line)
                
                for phrase in phrases:
                    phrase_flat = phrase.replace(" ", "")
                    line_search = line_flat.lower() if not case_sensitive else line_flat
                    phrase_search = phrase_flat.lower() if not case_sensitive else phrase_flat
                    
                    if not phrase_search:
                        continue
                        
                    start_char = line_search.find(phrase_search)
                    while start_char != -1:
                        end_char = start_char + len(phrase_search)
                        
                        # Get matching word ranges back from references index flat map
                        matched_word_indices = set(char_to_word_idx[start_char:end_char])
                        matched_rects = [words[i]['rect'] for i in matched_word_indices]
                        
                        if matched_rects:
                            big_rect = matched_rects[0]
                            for r in matched_rects[1:]:
                                big_rect |= r
                                
                            page_rect = big_rect * inv_mat
                            page_matches.append((phrase, page_rect))
                            
                        start_char = line_search.find(phrase_search, start_char + 1)
            
            return page_num, page_matches

        # Launch multithreading (Tesseract spawns subprocesses, bypassing GIL)
        completed_count = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = {executor.submit(_process_page, p_num): p_num for p_num in pages_to_process}
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    p_num, page_matches = future.result()
                    if page_matches:
                        matches[p_num] = page_matches
                except Exception as e:
                    # Log but preserve results from other pages
                    failed_page = futures[future]
                    print(f"OCR failed on page {failed_page + 1}: {e}")
                    
                completed_count += 1
                if progress_callback:
                    progress_callback(completed_count, len(pages_to_process))
                    
        return matches
