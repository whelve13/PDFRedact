import fitz
from PIL import Image
import pytesseract
from pytesseract import Output
import os
import sys
import re
from typing import List, Dict

from pdf_redactor.utils.resource_handler import get_resource_path

tess_path = get_resource_path(os.path.join('tesseract_bin', 'tesseract.exe'))
if os.path.exists(tess_path):
    pytesseract.pytesseract.tesseract_cmd = tess_path
else:
    # Fallback to system PATH if not bundled
    pass

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
            pix = page.get_pixmap(matrix=mat, alpha=False)
            mode = "RGBA" if pix.alpha else "RGB"
            img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
            local_doc.close()
            
            # --- OpenCV Preprocessing Pipeline ---
            open_cv_image = np.array(img) 
            if mode == "RGB":
                open_cv_image = open_cv_image[:, :, ::-1].copy() 
            elif mode == "RGBA":
                open_cv_image = cv2.cvtColor(open_cv_image, cv2.COLOR_RGBA2BGR)
                
            gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)
            denoised = cv2.fastNlMeansDenoising(gray, h=10)
            _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            page_matches = []
            data = pytesseract.image_to_data(binary, lang=lang, output_type=Output.DICT)
            
            # Logical Line grouping
            lines = {}
            for i in range(len(data['text'])):
                word_text = data['text'][i].strip()
                if int(data['conf'][i]) >= 0 and word_text:
                    key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
                    if key not in lines:
                        lines[key] = []
                    lines[key].append({
                        'text': word_text,
                        'left': data['left'][i],
                        'top': data['top'][i],
                        'width': data['width'][i],
                        'height': data['height'][i],
                    })
            
            for key, words in lines.items():
                line_text = " ".join([w['text'] for w in words])
                
                for phrase in phrases:
                    search_flags = 0 if case_sensitive else re.IGNORECASE
                    escaped_phrase = re.escape(phrase)
                    
                    for match in re.finditer(escaped_phrase, line_text, search_flags):
                        start_char = match.start()
                        end_char = match.end()
                        
                        current_char_idx = 0
                        matched_words = []
                        
                        for w in words:
                            word_start = current_char_idx
                            word_end = current_char_idx + len(w['text'])
                            
                            if word_start < end_char and word_end > start_char:
                                matched_words.append(w)
                            
                            current_char_idx = word_end + 1
                        
                        if matched_words:
                            min_x = min([w['left'] for w in matched_words])
                            min_y = min([w['top'] for w in matched_words])
                            max_x = max([w['left'] + w['width'] for w in matched_words])
                            max_y = max([w['top'] + w['height'] for w in matched_words])
                            
                            rect = fitz.Rect(
                                min_x * scale_factor,
                                min_y * scale_factor,
                                max_x * scale_factor,
                                max_y * scale_factor
                            )
                            page_matches.append((phrase, rect))
            
            return page_num, page_matches

        # Launch multithreading (Tesseract spawns subprocesses, bypassing GIL)
        completed_count = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = {executor.submit(_process_page, p_num): p_num for p_num in pages_to_process}
            
            for future in concurrent.futures.as_completed(futures):
                p_num, page_matches = future.result()
                if page_matches:
                    matches[p_num] = page_matches
                    
                completed_count += 1
                if progress_callback:
                    progress_callback(completed_count, len(pages_to_process))
                    
        return matches
