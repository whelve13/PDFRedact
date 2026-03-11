import fitz
import os
from typing import Dict, List
from pdf_redactor.core.redaction_styles import RedactionMode, STYLES

class RedactionEngine:
    """
    Applies redaction styles to PDF documents.
    """
    def __init__(self, pdf_path: str):
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        self.doc = fitz.open(pdf_path)

    def apply_redactions(self, matches: Dict[int, List[fitz.Rect]], mode: RedactionMode):
        """
        Applies the selected style to all target phrase bounding boxes.
        
        Args:
            matches: Dict mapping page number to list of bounding boxes.
            mode: The RedactionMode to apply.
        """
        style = STYLES[mode]
        
        for page_num, rects in matches.items():
            if page_num < 0 or page_num >= len(self.doc):
                continue
            
            page = self.doc[page_num]
            
            for rect in rects:
                if mode == RedactionMode.BLACK_BAR:
                    # True redaction: adds an annotation and applies it to destroy underlying text/imagery
                    page.add_redact_annot(rect, fill=style.fill)
                elif mode == RedactionMode.RED_BOX:
                    # Just draws a standard un-filled rectangle on top
                    page.draw_rect(rect, color=style.stroke, width=style.width)
                elif mode == RedactionMode.HIGHLIGHT:
                    # Add a highlight annotation overlay
                    annot = page.add_highlight_annot(rect)
                    annot.set_colors(stroke=style.fill)
                    annot.update()

            if mode == RedactionMode.BLACK_BAR:
                # Actually execute the text removal
                # Set images parameter to wipe pixels physically inside the bounding box
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)

    def save(self, output_path: str):
        """
        Saves the modified PDF to the given path, scrubbing metadata securely.
        """
        # Strip metadata to prevent information leaks
        self.doc.set_metadata({})
        
        # Save carefully to avoid leaking redacted data in history/metadata
        # Garbage collection is heavily required for files with removed text.
        self.doc.save(output_path, garbage=4, deflate=True)

    def close(self):
        """Releases the PDF document from memory."""
        self.doc.close()
