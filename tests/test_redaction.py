import pytest
import fitz
from pdf_redactor.core.redaction_engine import RedactionEngine
from pdf_redactor.core.redaction_styles import RedactionMode

@pytest.fixture
def mock_pdf(tmp_path):
    pdf_path = tmp_path / "mock.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Classified Information Here.")
    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)

def test_black_bar_redaction(mock_pdf, tmp_path):
    out_path = str(tmp_path / "redacted.pdf")
    
    doc = fitz.open(mock_pdf)
    rects = doc[0].search_for("Classified Information")
    doc.close()
    
    assert len(rects) > 0
    
    engine = RedactionEngine(mock_pdf)
    engine.apply_redactions({0: rects}, RedactionMode.BLACK_BAR)
    engine.save(out_path)
    engine.close()
    
    redacted_doc = fitz.open(out_path)
    text = redacted_doc[0].get_text("text")
    
    assert "Classified Information" not in text
    assert "Here." in text
    redacted_doc.close()
