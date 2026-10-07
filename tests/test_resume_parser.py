"""Tests for resume parsing and text extraction."""
import pytest
from backend.services.resume_parser import (
    validate_file,
    extract_text,
    FileValidationError,
    FileParsingError,
)

def test_validate_file_valid_txt():
    content = b"John Doe\nSoftware Engineer\nPython, FastAPI, Docker"
    is_valid, err, file_type = validate_file(content, "resume.txt")
    assert is_valid is True
    assert file_type == "txt"
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

def test_extract_text_txt():
    sample = "Alex Smith\nFull-Stack Developer\nSkills: React, Node.js, Python"
    text = extract_text(sample.encode("utf-8"), "txt")
    assert "Alex Smith" in text
    assert "Full-Stack Developer" in text

def test_extract_text_doc_raises_guidance():
    with pytest.raises(FileParsingError) as exc_info:
        extract_text(b"legacy word doc", "doc")
    assert "legacy .doc" in str(exc_info.value).lower()
