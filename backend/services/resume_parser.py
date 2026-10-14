"""
Resume Parser Service.

Handles multi-format resume file validation and text extraction (PDF, DOCX, TXT).
OCR-free native text extraction with resilient fallback logic (pypdf -> pdfplumber).
"""

from __future__ import annotations

import io
import logging
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple
import zipfile

# Decoupled primary and fallback PDF extractor imports
try:
    from pypdf import PdfReader
    import pypdf.errors as pypdf_errors
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False
    PdfReader = None
    pypdf_errors = None

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    pdfplumber = None

try:
    from docx import Document
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False
    Document = None

try:
    import magic
    HAS_MAGIC = True
except Exception:
    HAS_MAGIC = False
    magic = None

from backend.utils.file_utils import (
    ATSBaseError,
    FileParsingError,
    TextExtractionError,
    FileUploadError,
    log_error,
    log_warning,
    log_info,
)

from backend.core.config import (
    MAX_FILE_SIZE_BYTES,
    MAX_FILE_SIZE_MB,
    SUPPORTED_EXTENSIONS,
    SUPPORTED_MIME_TYPES,
)

logger = logging.getLogger('ats_resume_scorer')


# ────────────────────────────────────────────────────────────────
# Typed Exceptions
# ────────────────────────────────────────────────────────────────

class FileValidationError(ATSBaseError):
    """Raised when file fails validation (size, extension, or type mismatch)."""
    pass


class CorruptedPDFError(FileParsingError):
    """Raised when a PDF is truncated, corrupted, or structurally invalid."""
    def __init__(self, message: str = "Corrupted PDF", user_message: Optional[str] = None):
        default_msg = "The PDF appears to be corrupted or incomplete. Please export or download it again."
        super().__init__(message, user_message=user_message or default_msg)


class PasswordProtectedPDFError(FileParsingError):
    """Raised when a PDF is encrypted or password-protected."""
    def __init__(self, message: str = "Password protected PDF", user_message: Optional[str] = None):
        default_msg = "This PDF is password-protected. Please upload an unlocked PDF."
        super().__init__(message, user_message=user_message or default_msg)


class NoExtractableTextError(FileParsingError):
    """Raised when a PDF contains no extractable selectable text."""
    def __init__(self, message: str = "No extractable text", user_message: Optional[str] = None):
        default_msg = "No selectable text was found in this PDF. Scanned/image-only resumes are not supported."
        super().__init__(message, user_message=user_message or default_msg)


# ────────────────────────────────────────────────────────────────
# Content Sniffing and File Validation
# ────────────────────────────────────────────────────────────────

def _detect_file_type(file_data: bytes, filename: str) -> Optional[str]:
    """
    Detect actual file type using binary magic byte inspection with
    python-magic as an optional assistant. Does not rely solely on extension.
    """
    if not file_data:
        return None

    # 1. Pure-Python Magic Byte Sniffing
    # PDF signature: starts with %PDF-
    if file_data.startswith(b'%PDF-'):
        return 'pdf'

    # DOCX signature: ZIP file starting with PK\x03\x04
    if file_data.startswith(b'PK\x03\x04'):
        try:
            with io.BytesIO(file_data) as bio:
                if zipfile.is_zipfile(bio):
                    with zipfile.ZipFile(bio) as zf:
                        names = zf.namelist()
                        if any('word/' in n or '[Content_Types].xml' in n for n in names):
                            return 'docx'
        except Exception:
            pass
        # Fallback for valid zip with docx extension
        if Path(filename).suffix.lower() == '.docx':
            return 'docx'

    # Legacy DOC: OLE2 compound document signature
    if file_data.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
        return 'doc'

    # 2. python-magic if available and operational
    if HAS_MAGIC:
        try:
            mime = magic.from_buffer(file_data, mime=True)
            if mime in SUPPORTED_MIME_TYPES:
                return SUPPORTED_MIME_TYPES[mime]
        except Exception:
            pass

    # 3. Plain Text (ASCII / UTF-8 decodable without null bytes)
    sample = file_data[:4096]
    if b'\x00' not in sample:
        try:
            sample.decode('utf-8')
            return 'txt'
        except UnicodeDecodeError:
            try:
                sample.decode('latin-1')
                return 'txt'
            except Exception:
                pass

    return None


def validate_file(
    file_data: bytes,
    filename: str
) -> Tuple[bool, str, Optional[str]]:
    """
    Validate uploaded file size, empty status, extension allowlist,
    and actual binary content type.
    """
    # 1. Validate file size
    file_size_bytes = len(file_data)
    if file_size_bytes > MAX_FILE_SIZE_BYTES:
        size_mb = file_size_bytes / (1024 * 1024)
        return (
            False,
            (
                f"File size ({size_mb:.2f} MB) exceeds the maximum "
                f"of {MAX_FILE_SIZE_MB} MB. "
                "Please upload a smaller file or compress your resume."
            ),
            None,
        )

    # 2. Validate empty files
    if file_size_bytes == 0:
        return (
            False,
            "Uploaded file is empty. Please check the file you uploaded.",
            None,
        )

    # 3. Validate filename extension against allowlist
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS)).upper()
        return (
            False,
            (
                f"Unsupported file extension: {extension or '[none]'}. "
                f"Please upload one of: {supported}."
            ),
            None,
        )

    # 4. Detect actual binary file type
    detected_type = _detect_file_type(file_data, filename)

    if detected_type is None:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS)).upper()
        return (
            False,
            (
                f"Could not verify file format of '{filename}'. "
                f"Please ensure it is a valid document matching one of: {supported}."
            ),
            None,
        )

    # 5. Guard against misleading extensions (e.g., text or exe renamed to .pdf)
    expected_type = extension.lstrip('.')
    if expected_type == 'pdf' and detected_type != 'pdf':
        return (
            False,
            "File content does not match a valid PDF file. Please ensure it is not corrupted or renamed.",
            None,
        )
    if expected_type == 'docx' and detected_type != 'docx':
        return (
            False,
            "File content does not match a valid DOCX document.",
            None,
        )

    return True, "", detected_type


# ────────────────────────────────────────────────────────────────
# Text Quality Assessment
# ────────────────────────────────────────────────────────────────

def is_usable_text(text: str) -> bool:
    """
    Evaluate whether extracted text contains meaningful resume content.
    Requires at least 50 non-whitespace characters and at least 30 alphabetic characters.
    """
    if not text or not isinstance(text, str):
        return False

    cleaned = " ".join(text.split())
    if len(cleaned) < 50:
        return False

    alphabetic = sum(ch.isalpha() for ch in cleaned)
    return alphabetic >= 30


# ────────────────────────────────────────────────────────────────
# PDF Text Extraction Pipeline
# ────────────────────────────────────────────────────────────────

def _extract_pdf_hyperlinks(file_data: bytes) -> str:
    """Extract actionable web hyperlinks from PDF annotations without OCR."""
    urls = []
    if not HAS_PYPDF:
        return ""
    try:
        reader = PdfReader(io.BytesIO(file_data))
        for page in reader.pages:
            try:
                annots = page.get('/Annots')
                if not annots:
                    continue
                for annot_ref in annots:
                    try:
                        annot = annot_ref.get_object()
                        if annot.get('/Subtype') != '/Link':
                            continue
                        action = annot.get('/A', {})
                        uri = action.get('/URI', '')
                        if uri and isinstance(uri, bytes):
                            uri = uri.decode('utf-8', errors='ignore')
                        uri = str(uri).strip()
                        if uri.startswith('http'):
                            urls.append(uri)
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception:
        pass
    return '\n'.join(urls)


def extract_text_from_pdf(file_data: bytes) -> str:
    """
    Extract text from a PDF without OCR.

    Pipeline:
    1. Validation of PDF header.
    2. Primary extraction via pypdf.PdfReader.
    3. Check for encryption / password-protection.
    4. Text quality assessment via is_usable_text().
    5. Fallback to pdfplumber if pypdf fails or produces insufficient text.
    6. Assessment of fallback text.
    7. Return usable text with hyperlinks or raise typed parsing error.
    """
    if not file_data or not file_data.startswith(b'%PDF-'):
        raise CorruptedPDFError(
            "File is not a valid PDF document.",
            user_message="The PDF appears to be corrupted or incomplete. Please export or download it again."
        )

    is_encrypted_flag = False
    pypdf_error_encountered = None
    extracted_text = ""

    # ==========================================================
    # Strategy 1: pypdf (Primary Extractor)
    # ==========================================================
    if HAS_PYPDF:
        try:
            reader = PdfReader(BytesIO(file_data))

            if reader.is_encrypted:
                is_encrypted_flag = True
                try:
                    # Attempt empty password decryption
                    decrypt_res = reader.decrypt("")
                    if decrypt_res == 0:
                        raise PasswordProtectedPDFError()
                except Exception:
                    raise PasswordProtectedPDFError()

            pages_text = []
            for page in reader.pages:
                try:
                    p_text = page.extract_text() or ""
                    if p_text.strip():
                        pages_text.append(p_text)
                except Exception as page_err:
                    log_warning(f"pypdf isolated page extraction failure: {page_err}", context="resume_parser")
                    continue

            pypdf_result = "\n".join(pages_text).strip()
            if is_usable_text(pypdf_result):
                extracted_text = pypdf_result
                log_info(f"pypdf extracted {len(extracted_text)} chars from {len(reader.pages)} page(s)", context="resume_parser")

        except PasswordProtectedPDFError:
            raise
        except Exception as exc:
            pypdf_error_encountered = exc
            log_warning(f"pypdf primary extraction failed: {type(exc).__name__}: {exc}", context="resume_parser")

    # If primary extraction succeeded with usable text, append links and return immediately
    if extracted_text and is_usable_text(extracted_text):
        links = _extract_pdf_hyperlinks(file_data)
        if links:
            extracted_text = extracted_text + "\n" + links
        return extracted_text.strip()

    # ==========================================================
    # Strategy 2: pdfplumber (Fallback Extractor)
    # ==========================================================
    if HAS_PDFPLUMBER:
        try:
            pages_text = []
            with pdfplumber.open(BytesIO(file_data)) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    try:
                        p_text = page.extract_text() or ""
                        if p_text.strip():
                            pages_text.append(p_text)
                    except Exception as page_err:
                        log_warning(f"pdfplumber isolated page {page_num} failure: {page_err}", context="resume_parser")
                        continue

            plumber_result = "\n".join(pages_text).strip()
            if is_usable_text(plumber_result):
                log_info(f"pdfplumber fallback extracted {len(plumber_result)} chars", context="resume_parser")
                links = _extract_pdf_hyperlinks(file_data)
                if links:
                    plumber_result = plumber_result + "\n" + links
                return plumber_result.strip()

        except Exception as exc:
            log_warning(f"pdfplumber fallback failed: {type(exc).__name__}: {exc}", context="resume_parser")

    # ==========================================================
    # Diagnostic Error Classification
    # ==========================================================
    if is_encrypted_flag:
        raise PasswordProtectedPDFError()

    if pypdf_error_encountered is not None:
        err_str = str(pypdf_error_encountered).lower()
        if "password" in err_str or "encrypted" in err_str:
            raise PasswordProtectedPDFError()
        if "truncated" in err_str or "eof" in err_str or "stream" in err_str:
            raise CorruptedPDFError()

    # If neither extractor raised an exception but no usable text was found
    raise NoExtractableTextError()


# ────────────────────────────────────────────────────────────────
# DOCX and TXT Extraction
# ────────────────────────────────────────────────────────────────

def extract_text_from_docx(file_data: bytes) -> str:
    """Extract text and hyperlinks from a modern .docx file."""
    if not HAS_DOCX:
        raise TextExtractionError(
            "python-docx is not installed",
            user_message="DOCX extraction engine unavailable on server."
        )

    try:
        doc = Document(io.BytesIO(file_data))
        text_parts = []

        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text_parts.append(paragraph.text)

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        text_parts.append(cell.text)

        text = '\n'.join(text_parts).strip()

        if not text:
            raise FileParsingError(
                'No text could be extracted from the document. The document may be empty or corrupted.',
                user_message='No text could be extracted from this DOCX document.'
            )

        # Extract hyperlinks
        try:
            for rel in doc.part.rels.values():
                if 'hyperlink' in rel.reltype.lower():
                    url = rel._target
                    if isinstance(url, str) and url.startswith('http'):
                        text += '\n' + url
        except Exception:
            pass

        log_info(f'Extracted {len(text)} chars from DOCX', context='resume_parser')
        return text

    except FileParsingError:
        raise
    except Exception as e:
        log_error(e, context='extract_text_from_docx')
        raise FileParsingError(
            f'Failed to extract text from DOCX: {e}',
            user_message='The DOCX file appears to be corrupted. Please export or save it again.'
        ) from e


def extract_text_from_doc(file_data: bytes) -> str:
    """Reject legacy .doc with helpful guidance."""
    raise FileParsingError(
        'Legacy .doc format is not supported. Please convert your document to .docx or .pdf and try again.',
        user_message='Legacy .doc format is not supported. Please convert your document to .docx or .pdf and try again.'
    )


def extract_text(file_data: bytes, file_type: str) -> str:
    """Route file to appropriate text extractor."""
    if file_type == 'pdf':
        return extract_text_from_pdf(file_data)
    elif file_type == 'docx':
        return extract_text_from_docx(file_data)
    elif file_type == 'doc':
        return extract_text_from_doc(file_data)
    elif file_type == 'txt':
        try:
            return file_data.decode('utf-8').strip()
        except UnicodeDecodeError:
            return file_data.decode('latin-1', errors='replace').strip()
    else:
        raise FileValidationError(
            f'Invalid file type: {file_type}. Supported types are: pdf, docx, txt, and doc.'
        )


def parse_resume_file(file_data: bytes, filename: str) -> Tuple[str, dict]:
    """
    Validate and extract text from an uploaded resume file.
    Returns (extracted_text, metadata_dict).
    """
    log_info(f'Validating and parsing file: {filename}', context='resume_parser')

    # Phase 1: Validate file
    is_valid, error_msg, file_type = validate_file(file_data, filename)
    if not is_valid:
        log_warning(f'Validation failed for file {filename}: {error_msg}', context='resume_parser')
        raise FileValidationError(error_msg, user_message=error_msg)

    # Phase 2: Extract text
    try:
        text = extract_text(file_data, file_type)  # type: ignore[arg-type]
        log_info(f'Extracted {len(text)} chars from {filename}', context='resume_parser')
    except (FileValidationError, FileParsingError):
        raise
    except Exception as e:
        log_error(e, context='resume_parser_extraction')
        raise FileParsingError(
            f'Failed to extract text from the resume: {e}',
            user_message='Could not extract readable text from your resume file.'
        ) from e

    metadata = {
        'filename': filename,
        'file_type': file_type,
        'file_size_bytes': len(file_data),
        'text_length': len(text),
        'success': True,
    }
    return text, metadata
