import pytest
import fitz
from pdf_redactor.core.pdf_parser import PDFParser

@pytest.fixture
def sample_pdf(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "This is a Highly Confidential document.")
    page.insert_text((50, 70), "It contains top secret test data.")
    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)

def test_has_text_layer(sample_pdf):
    parser = PDFParser(sample_pdf)
    assert parser.has_text_layer(0) is True
    parser.close()

def test_find_phrases_case_insensitive(sample_pdf):
    parser = PDFParser(sample_pdf)
    matches = parser.find_phrases(["highly confidential", "secret"])
    assert 0 in matches
    assert len(matches[0]) >= 2
    parser.close()

def test_find_phrases_case_sensitive(sample_pdf):
    parser = PDFParser(sample_pdf)
    matches_fail = parser.find_phrases(["highly confidential"], case_sensitive=True)
    assert not matches_fail or len(matches_fail.get(0, [])) == 0
    
    matches_success = parser.find_phrases(["Highly Confidential"], case_sensitive=True)
    assert 0 in matches_success
    assert len(matches_success[0]) >= 2 # Evaluates as multiple word bounding rects
    parser.close()
