# Phase 1 Audit: Resume Parser Stabilization & Test Suite Robustness

## 1. Executive Summary

This audit examines the resume extraction and validation pipeline in `backend/services/resume_parser.py`, `backend/core/config.py`, and `backend/api/routes.py`. The goal of Phase 1 is to stabilize native PDF/DOCX/TXT text extraction, eliminate platform-specific dependency crashes, implement clear typed error handling, remove debugging prints, and establish thorough unit and regression tests without using OCR.

---

## 2. Codebase Audit Findings

### 2.1 File Validation & MIME Type Detection
- **Issue**: In `backend/services/resume_parser.py`, `validate_file()` calls `magic.from_buffer(file_data, mime=True)`. When `python-magic` C libraries are unavailable (such as Windows environments lacking `python-magic-bin` or libmagic DLLs), `HAS_MAGIC` is set to `False`, and calling `magic.from_buffer()` raises an unhandled `NameError: name 'magic' is not defined`.
- **Impact**: Any valid upload (`.txt`, `.pdf`, `.docx`) fails with `Error determining file type: name 'magic' is not defined`, returning HTTP 422 to the client.
- **Fix**: Implement deterministic pure-Python signature sniffing (magic byte inspection) as a primary or graceful fallback:
  - PDF: starts with `%PDF-` (`b"%PDF-"`).
  - DOCX: starts with PK zip header (`b"PK\x03\x04"`) containing Word XML structures.
  - DOC: OLE2 compound document header `b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"`.
  - TXT: printable UTF-8/ASCII bytes without null bytes.

### 2.2 PDF Extraction & Fallback Coupling
- **Issue**: In `backend/services/resume_parser.py` lines 6–11:
  ```python
  try:
      import pdfplumber
      from pypdf import PdfReader
      HAS_PDFPLUMBER = True
  except ImportError:
      HAS_PDFPLUMBER = False
  ```
  Both `pdfplumber` and `pypdf.PdfReader` were placed in a single `try` block. If `pdfplumber` was missing or threw an import error, `PdfReader` was never imported, completely breaking pypdf extraction as well.
- **Fix**: Decouple library imports so `pypdf` and `pdfplumber` are imported independently.

### 2.3 Text Quality Assessment (`is_usable_text`)
- **Issue**: `is_usable_text()` was defined at the bottom of `resume_parser.py` (checking `len >= 50` and `alphabetic >= 30`), but `extract_text_from_pdf()` did not use it. Instead, it used a naive `len(extracted_text) >= 50` check, which accepted strings with whitespace, punctuation, or non-alphabetic noise.
- **Fix**: Integrate `is_usable_text()` into the PDF extraction pipeline. Only accept extractions from `pypdf` if `is_usable_text(extracted_text)` returns `True`. If not, fall back to `pdfplumber`. If `pdfplumber` also fails `is_usable_text()`, raise an informative `NoExtractableTextError`.

### 2.4 Error Classification & Typed Exceptions
- **Issue**: When PDF parsing failed, a generic `ValueError` was raised, bundling scanned PDFs, corrupted files, and password-protected files together.
- **Fix**: Introduce typed exceptions inheriting from `FileParsingError`:
  - `PasswordProtectedPDFError`: "This PDF is password-protected. Please upload an unlocked PDF."
  - `CorruptedPDFError`: "The PDF appears to be corrupted or incomplete. Please export or download it again."
  - `NoExtractableTextError`: "No selectable text was found in this PDF. Scanned/image-only resumes are not supported."
  - `EmptyFileUploadError`: "Uploaded file is empty. Please check the file you uploaded."
  - `FileTooLargeError`: "File size exceeds the maximum limit."

### 2.5 Debug Prints & Leaked Tracebacks
- **Issue**: `resume_parser.py` contained numerous `print()` statements (`[PDF] pypdf extracted...`, `[PDF] pdfplumber page...`) and printed stack traces to stdout via `traceback.print_exc()`.
- **Fix**: Replace all debugging prints with project-standard logger calls (`log_info`, `log_warning`, `log_error`), ensuring sensitive user content and tokens are never printed or logged.

### 2.6 API Route Error Propagation
- **Issue**: `backend/api/routes.py` caught generic `Exception` and returned `Could not read or parse the resume: {exc}` with HTTP 422, exposing internal Python exception strings.
- **Fix**: Catch `FileValidationError` returning HTTP 400 with user-facing messages, and catch `FileParsingError` returning HTTP 422 with actionable messages. Keep raw tracebacks strictly in server logs.

---

## 3. Implementation Roadmap

1. **Refactor `validate_file()`**:
   - Verify file size (`MAX_FILE_SIZE_BYTES`).
   - Reject empty files (0 bytes).
   - Verify file extension against `SUPPORTED_EXTENSIONS`.
   - Sniff magic bytes / content signature with pure-Python fallback.
   - Return `(is_valid, error_message, detected_file_type)`.

2. **Implement Resilient Native PDF Extraction**:
   - Independent import of `pypdf.PdfReader` and `pdfplumber`.
   - Check for password protection (`reader.is_encrypted`).
   - Page-by-page extraction with isolation (one failing page does not abort remaining pages).
   - Validate extracted text quality with `is_usable_text()`.
   - Fall back to `pdfplumber` if `pypdf` raises an error or fails quality check.
   - Extract hyperlinks and append to text if present.
   - If both fail, raise specific typed exceptions (`PasswordProtectedPDFError`, `CorruptedPDFError`, or `NoExtractableTextError`).

3. **Preserve DOCX and TXT Extraction**:
   - Ensure `extract_text_from_docx()` and TXT decode logic remain fully functional.
   - Provide clear rejection for legacy `.doc` files directing users to `.docx` or `.pdf`.

4. **Clean Logging & Error Responses**:
   - Eliminate all raw `print()` statements.
   - Refine exception handlers in `backend/api/routes.py`.

5. **Comprehensive Tests**:
   - Unit tests covering all branches in `tests/test_resume_parser.py`.
   - Integration tests in `tests/test_api.py` with offline mocks.
