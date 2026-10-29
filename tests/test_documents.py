import io
import pytest
from app.services.document_parser import (
    DocumentParserService,
    DocumentParsingError,
    ScannedDocumentError,
    normalize_extracted_text,
)


def test_normalize_extracted_text():
    raw = "  Hello \xa0 world! \n\n\n\n This is a   test. \r\n Line two. "
    normalized = normalize_extracted_text(raw)
    assert "Hello world!" in normalized
    assert "Line two." in normalized
    assert "\xa0" not in normalized
    assert "\r" not in normalized


def test_extract_pdf_success(sample_pdf_bytes):
    stream = io.BytesIO(sample_pdf_bytes)
    text = DocumentParserService.extract_from_pdf(stream)
    assert "John Doe" in text
    assert "Content Creator" in text
    assert "Increased organic traffic" in text


def test_extract_pdf_scanned_error(sample_scanned_pdf_bytes):
    stream = io.BytesIO(sample_scanned_pdf_bytes)
    with pytest.raises(ScannedDocumentError) as exc_info:
        DocumentParserService.extract_from_pdf(stream)
    assert "scanned or image-based" in str(exc_info.value).lower()


def test_extract_docx_success(sample_docx_bytes):
    stream = io.BytesIO(sample_docx_bytes)
    text = DocumentParserService.extract_from_docx(stream)
    assert "Senior Content Strategist" in text
    assert "Responsibilities" in text


def test_extract_txt_success():
    stream = io.BytesIO(b"Job Title: Technical Writer\nKey Duties: Documentation, guides, release notes.")
    text = DocumentParserService.extract_from_txt(stream)
    assert "Technical Writer" in text
    assert "release notes" in text


def test_extract_empty_txt_error():
    stream = io.BytesIO(b"   \n  \t  ")
    with pytest.raises(DocumentParsingError):
        DocumentParserService.extract_from_txt(stream)


def test_unsupported_file_extension():
    with pytest.raises(DocumentParsingError) as exc_info:
        DocumentParserService.extract_text(io.BytesIO(b"some content"), filename="test.exe")
    assert "unsupported file format" in str(exc_info.value).lower()
