import fitz
import os
from typing import List, Dict, Optional

class PDFParser:
    """
    Handles PDF loading, text layer detection, and phrase coordinate extraction.
    """
    def __init__(self, file_path: str):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found: {file_path}")
        self.file_path = file_path
        self.doc = fitz.open(file_path)

    def has_text_layer(self, page_num: int) -> bool:
        """
        Checks if a specific page contains extractable text.
        """
        if page_num < 0 or page_num >= len(self.doc):
            raise ValueError("Invalid page number")
        page = self.doc[page_num]
        text = page.get_text("text").strip()
        return len(text) > 0

    def get_all_pages_text_status(self) -> Dict[int, bool]:
        """
        Returns a dictionary mapping page index to whether it has a text layer.
        """
        status = {}
        for i in range(len(self.doc)):
            status[i] = self.has_text_layer(i)
        return status

    def find_phrases(self, phrases: List[str], case_sensitive: bool = False) -> Dict[int, List[tuple]]:
        """
        Searches for phrases in the PDF and returns their bounding boxes per page.
        Uses word-level positional mapping to support phrases split across multiple lines.
        Returns:
            A dictionary mapping page_num -> list of (phrase_matched, fitz.Rect) for matches.
        """
        import re
        matches = {}
        for page_num in range(len(self.doc)):
            page = self.doc[page_num]
            page_matches = []
            
            # Extract all words: (x0, y0, x1, y1, "word", block_no, line_no, word_no)
            words = page.get_text("words")
            if not words:
                continue
                
            # Reconstruct string with index tracking
            full_text = " ".join([w[4] for w in words])
            
            for phrase in phrases:
                flags = 0 if case_sensitive else re.IGNORECASE
                escaped = re.escape(phrase)
                
                for match in re.finditer(escaped, full_text, flags):
                    start_char = match.start()
                    end_char = match.end()
                    
                    curr_len = 0
                    matched_rects = []
                    
                    for w in words:
                        word_text = w[4]
                        w_start = curr_len
                        w_end = curr_len + len(word_text)
                        
                        # Overlap check
                        if w_start < end_char and w_end > start_char:
                            rect = fitz.Rect(w[0], w[1], w[2], w[3])
                            matched_rects.append((phrase, rect))
                            
                        curr_len = w_end + 1 # Account for the joining space
                        
                        if curr_len > end_char:
                            break
                            
                    page_matches.extend(matched_rects)
            
            if page_matches:
                matches[page_num] = page_matches
                
        return matches

    def close(self):
        """Closes the PDF document."""
        self.doc.close()
