"""
Comprehensive unit and regression tests for resume parsing, file validation,
and native PDF/DOCX/TXT text extraction pipelines.
"""

import io
from unittest.mock import MagicMock, patch
import pytest
from pypdf import PdfWriter

from backend.services.resume_parser import (
    validate_file,
    extract_text,
    extract_text_from_pdf,
    extract_text_from_docx,
    parse_resume_file,
    is_usable_text,
    FileValidationError,
    FileParsingError,
    CorruptedPDFError,
    PasswordProtectedPDFError,
    NoExtractableTextError,
)

# ────────────────────────────────────────────────────────────────
# Helpers to generate synthetic in-memory test documents
# ────────────────────────────────────────────────────────────────

def create_synthetic_blank_pdf(num_pages: int = 1) -> bytes:
    """Create a minimal valid PDF without extractable text."""
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=200, height=200)
    bio = io.BytesIO()
    writer.write(bio)
    return bio.getvalue()


def create_synthetic_encrypted_pdf(password: str = "secret123") -> bytes:
    """Create a password-protected PDF in memory."""
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt(password)
    bio = io.BytesIO()
    writer.write(bio)
    return bio.getvalue()


def create_synthetic_docx(text: str) -> bytes:
    """Create a valid in-memory DOCX document."""
    from docx import Document
    doc = Document()
    for paragraph in text.split("\n"):
        if paragraph.strip():
            doc.add_paragraph(paragraph)
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()


# ────────────────────────────────────────────────────────────────
# File Validation Tests
# ────────────────────────────────────────────────────────────────

def test_validate_file_valid_txt():
    content = b"John Doe\nSoftware Engineer\nPython, FastAPI, Docker"
    is_valid, err, file_type = validate_file(content, "resume.txt")
    assert is_valid is True
    assert file_type == "txt"
    assert err == ""


def test_validate_file_valid_pdf():
    content = create_synthetic_blank_pdf()
    is_valid, err, file_type = validate_file(content, "resume.pdf")
    assert is_valid is True
    assert file_type == "pdf"
    assert err == ""


def test_validate_file_valid_docx():
    content = create_synthetic_docx("Jane Doe\nBackend Developer")
    is_valid, err, file_type = validate_file(content, "resume.docx")
    assert is_valid is True
    assert file_type == "docx"
    assert err == ""


def test_validate_file_empty():
    is_valid, err, file_type = validate_file(b"", "resume.pdf")
    assert is_valid is False
    assert "empty" in err.lower()


def test_validate_file_exceeds_size():
    oversized = b"x" * (6 * 1024 * 1024)  # 6 MB (max is 5 MB)
    is_valid, err, file_type = validate_file(oversized, "resume.pdf")
    assert is_valid is False
    assert "exceeds" in err.lower()


def test_validate_file_unsupported_extension():
    content = b"image content"
    is_valid, err, file_type = validate_file(content, "resume.exe")
    assert is_valid is False
    assert "unsupported file extension" in err.lower()


def test_validate_file_mismatched_content():
    # File named .pdf but contains plain text without %PDF- header
    fake_pdf = b"This is just a text file renamed to resume.pdf"
    is_valid, err, file_type = validate_file(fake_pdf, "resume.pdf")
    assert is_valid is False
    assert "does not match a valid pdf" in err.lower()


# ────────────────────────────────────────────────────────────────
# Text Quality Rules (is_usable_text)
# ────────────────────────────────────────────────────────────────

def test_is_usable_text_rules():
    assert not is_usable_text("")
    assert not is_usable_text("   \n\t  ")
    # Less than 50 chars
    assert not is_usable_text("Short text")
    # 50+ chars but lacking alphabetic content (<30 letters)
    assert not is_usable_text("----------------- 1234567890 ------------------ !@#$%^&*()_+")
    # Valid resume text
    valid_text = "Jane Doe - Senior Python Software Engineer with experience in cloud microservices."
    assert is_usable_text(valid_text)


# ────────────────────────────────────────────────────────────────
# PDF Extraction Pipeline & Fallback Tests
# ────────────────────────────────────────────────────────────────

def test_extract_pdf_pypdf_primary_success():
    """Verify primary extraction using pypdf when text is usable."""
    pdf_bytes = create_synthetic_blank_pdf(1)
    sample_text = "Jane Doe\nSenior Backend Engineer\nExtensive experience building APIs in Python and FastAPI."

    mock_page = MagicMock()
    mock_page.extract_text.return_value = sample_text
    mock_page.get.return_value = None

    with patch("backend.services.resume_parser.PdfReader") as mock_reader_cls:
        mock_reader = MagicMock()
        mock_reader.is_encrypted = False
        mock_reader.pages = [mock_page]
        mock_reader_cls.return_value = mock_reader

        result = extract_text_from_pdf(pdf_bytes)
        assert "Jane Doe" in result
        assert "FastAPI" in result


def test_extract_pdf_pypdf_insufficient_text_pdfplumber_fallback_success():
    """Regression test: when pypdf returns insufficient text, pdfplumber fallback succeeds."""
    pdf_bytes = create_synthetic_blank_pdf(1)
    good_text = "Alex Smith\nSoftware Engineer with experience in distributed computing and Python microservices."

    # pypdf returns text too short (<50 chars)
    mock_pypdf_page = MagicMock()
    mock_pypdf_page.extract_text.return_value = "Page 1"
    mock_pypdf_page.get.return_value = None

    # pdfplumber returns good text
    mock_plumber_page = MagicMock()
    mock_plumber_page.extract_text.return_value = good_text

    mock_pdfplumber = MagicMock()
    mock_pdf_ctx = MagicMock()
    mock_pdf_ctx.pages = [mock_plumber_page]
    mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf_ctx

    with patch("backend.services.resume_parser.HAS_PDFPLUMBER", True), \
         patch("backend.services.resume_parser.PdfReader") as mock_pypdf_cls, \
         patch("backend.services.resume_parser.pdfplumber", mock_pdfplumber):

        mock_pypdf = MagicMock()
        mock_pypdf.is_encrypted = False
        mock_pypdf.pages = [mock_pypdf_page]
        mock_pypdf_cls.return_value = mock_pypdf

        result = extract_text_from_pdf(pdf_bytes)
        assert "Alex Smith" in result
        assert "distributed computing" in result


def test_extract_pdf_pypdf_exception_pdfplumber_fallback_success():
    """When pypdf raises an exception, pdfplumber fallback succeeds without crashing."""
    pdf_bytes = create_synthetic_blank_pdf(1)
    good_text = "Morgan Freeman\nData Scientist with deep learning and natural language processing experience."

    mock_plumber_page = MagicMock()
    mock_plumber_page.extract_text.return_value = good_text

    mock_pdfplumber = MagicMock()
    mock_pdf_ctx = MagicMock()
    mock_pdf_ctx.pages = [mock_plumber_page]
    mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf_ctx

    with patch("backend.services.resume_parser.HAS_PDFPLUMBER", True), \
         patch("backend.services.resume_parser.PdfReader", side_effect=Exception("pypdf parsing error")), \
         patch("backend.services.resume_parser.pdfplumber", mock_pdfplumber):

        result = extract_text_from_pdf(pdf_bytes)
        assert "Morgan Freeman" in result
        assert "Data Scientist" in result


def test_extract_pdf_multiple_pages():
    """Verify multi-page PDF extraction accumulates all pages."""
    pdf_bytes = create_synthetic_blank_pdf(2)

    page1 = MagicMock()
    page1.extract_text.return_value = "Page 1 content: Alice Smith software engineering lead at TechCo."
    page1.get.return_value = None

    page2 = MagicMock()
    page2.extract_text.return_value = "Page 2 content: Education B.S. Computer Science State University."
    page2.get.return_value = None

    with patch("backend.services.resume_parser.PdfReader") as mock_reader_cls:
        mock_reader = MagicMock()
        mock_reader.is_encrypted = False
        mock_reader.pages = [page1, page2]
        mock_reader_cls.return_value = mock_reader

        result = extract_text_from_pdf(pdf_bytes)
        assert "Page 1 content" in result
        assert "Page 2 content" in result


def test_extract_pdf_isolated_page_error_continues():
    """When one page raises an extraction error, remaining pages are still extracted."""
    pdf_bytes = create_synthetic_blank_pdf(2)

    bad_page = MagicMock()
    bad_page.extract_text.side_effect = Exception("Corrupt stream on page 1")
    bad_page.get.return_value = None

    good_page = MagicMock()
    good_page.extract_text.return_value = "Page 2: Valid career history and technical projects in Python and AWS."
    good_page.get.return_value = None

    with patch("backend.services.resume_parser.PdfReader") as mock_reader_cls:
        mock_reader = MagicMock()
        mock_reader.is_encrypted = False
        mock_reader.pages = [bad_page, good_page]
        mock_reader_cls.return_value = mock_reader

        result = extract_text_from_pdf(pdf_bytes)
        assert "Page 2: Valid career history" in result


def test_extract_pdf_no_extractable_text():
    """A blank or image-only PDF raises NoExtractableTextError."""
    pdf_bytes = create_synthetic_blank_pdf(1)
    with pytest.raises(NoExtractableTextError) as exc_info:
        extract_text_from_pdf(pdf_bytes)
    assert "no selectable text" in str(exc_info.value.user_message).lower()


def test_extract_pdf_corrupted_header():
    """A non-PDF file raises CorruptedPDFError."""
    corrupted_bytes = b"Not a real PDF file content at all"
    with pytest.raises(CorruptedPDFError) as exc_info:
        extract_text_from_pdf(corrupted_bytes)
    assert "corrupted" in str(exc_info.value.user_message).lower()


def test_extract_pdf_password_protected():
    """An encrypted PDF raises PasswordProtectedPDFError."""
    encrypted_bytes = create_synthetic_encrypted_pdf("mypassword")
    with pytest.raises(PasswordProtectedPDFError) as exc_info:
        extract_text_from_pdf(encrypted_bytes)
    assert "password" in str(exc_info.value.user_message).lower()


# ────────────────────────────────────────────────────────────────
# DOCX and TXT Extraction Tests
# ────────────────────────────────────────────────────────────────

def test_extract_text_txt():
    sample = "Alex Smith\nFull-Stack Developer\nSkills: React, Node.js, Python"
    text = extract_text(sample.encode("utf-8"), "txt")
    assert "Alex Smith" in text
    assert "Full-Stack Developer" in text


def test_extract_text_docx():
    docx_bytes = create_synthetic_docx(
        "John Doe\nLead Engineer\nDemonstrated expertise in Python, Docker, and PostgreSQL microservices."
    )
    text = extract_text_from_docx(docx_bytes)
    assert "John Doe" in text
    assert "Lead Engineer" in text
    assert "PostgreSQL" in text


def test_extract_text_doc_raises_guidance():
    with pytest.raises(FileParsingError) as exc_info:
        extract_text(b"legacy word doc", "doc")
    assert "legacy .doc" in str(exc_info.value).lower()


def test_parse_resume_file_success_and_metadata():
    txt_content = (
        "Jane Doe\njane@example.com\n\n"
        "Summary\nSenior software engineer with 5 years experience in building APIs.\n\n"
        "Skills\nPython, FastAPI, Docker, SQL\n"
    ).encode("utf-8")

    text, metadata = parse_resume_file(txt_content, "resume.txt")
    assert "Jane Doe" in text
    assert metadata["filename"] == "resume.txt"
    assert metadata["file_type"] == "txt"
    assert metadata["file_size_bytes"] == len(txt_content)
    assert metadata["success"] is True
