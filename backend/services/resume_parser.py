from PIL import EpsImagePlugin
import io
from typing import Optional, Tuple
from io import BytesIO
from pathlib import Path
try:
    import pdfplumber
    from pypdf import PdfReader
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
from docx import Document
import PyPDF2

try:
    import magic
    HAS_MAGIC = True
except Exception:
    HAS_MAGIC = False

from backend.utils.file_utils import (
    FileParsingError, 
    TextExtractionError, 
    FileUploadError, 
    log_error, 
    log_warning, 
    log_info, 
    with_fallback
)

from backend.core.config import (
    MAX_FILE_SIZE_BYTES,
    MAX_FILE_SIZE_MB,
    SUPPORTED_EXTENSIONS,
    SUPPORTED_MIME_TYPES,
)

class FileValidationError(Exception):
    pass


def validate_file(
    file_data: bytes,
    filename: str
) -> Tuple[bool, str, Optional[str]]:
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

    # 3. Validate filename extension
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

    # 4. Detect actual MIME type
    try:
        mime_type = magic.from_buffer(file_data, mime=True)
    except Exception as e:
        return False, f"Error determining file type: {e}", None

    # 5. Validate MIME type
    if mime_type not in SUPPORTED_MIME_TYPES:
        supported = ", ".join(
            SUPPORTED_MIME_TYPES.keys()
        ).upper()

        return (
            False,
            (
                f"Unsupported file type: {mime_type}. "
                f"Please upload one of: {supported}."
            ),
            None,
        )

    # 6. Return validated file type
    file_type = SUPPORTED_MIME_TYPES[mime_type]

    return True, "", file_type

def _extract_pdf_hyperlinks(file_data: bytes) -> str:
    urls = []
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(file_data))
        for page in reader.pages:
            if '/Annots' not in page:
                continue
            for annot_ref in page['/Annots']:
                try:
                    annot = annot_ref.get_object()
                    if annot.get('/Subtype') != '/Link':
                        continue
                    action = annot.get('/A', {})
                    uri = action.get('/URI', '')
                    if uri and isinstance(uri, (str, bytes)):
                        # PyPDF2 may return bytes for URI values
                        if isinstance(uri, bytes):
                            uri = uri.decode('utf-8', errors='ignore')
                        uri = uri.strip()
                        if uri.startswith('http'):
                            urls.append(uri)
                except Exception:
                    pass
    except Exception:
        pass
    return '\n'.join(urls)


def _extract_pdf_with_pdfplumber(file_data: bytes) -> str:
    if not HAS_PDFPLUMBER:
        raise TextExtractionError(
            'pdfplumber is not installed',
            user_message='PDF extraction engine pdfplumber unavailable.'
        )
    text = ''
    with pdfplumber.open(io.BytesIO(file_data)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + '\n'

    if not text.strip():
        raise TextExtractionError(
            'pdfplumber extracted no text',
            user_message='No text could be extracted from the PDF.'
        )
    
    hyperlinks = _extract_pdf_hyperlinks(file_data)
    if hyperlinks:
        text = text.strip() + '\n' + hyperlinks

    return text.strip()


def _extract_pdf_with_pypdf2(file_data: bytes) -> str:
    text = ''
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_data))
    for page in pdf_reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + '\n'

    if not text.strip():
        raise TextExtractionError(
            'PyPDF2 extracted no text',
            user_message='No text could be extracted from the PDF.'
        )

    hyperlinks = _extract_pdf_hyperlinks(file_data)
    if hyperlinks:
        text = text.strip() + '\n' + hyperlinks

    return text.strip()

def extract_text_from_pdf(file_data: bytes) -> str:
    """
    Extract text from a PDF without OCR.

    Strategy:
    1. Try pypdf.
    2. If pypdf fails or produces insufficient text, try pdfplumber.
    3. Reject the PDF only when neither extractor produces usable text.
    """

    # ==========================================================
    # Strategy 1: pypdf
    # ==========================================================
    try:
        reader = PdfReader(BytesIO(file_data))

        pages_text = []

        for page in reader.pages:
            try:
                page_text = page.extract_text() or ""

                if page_text.strip():
                    pages_text.append(page_text)

            except Exception:
                # One bad page should not prevent other pages
                continue

        extracted_text = "\n".join(pages_text).strip()

        print(
            f"[PDF] pypdf extracted {len(extracted_text)} characters"
        )

        if len(extracted_text) >= 50:
            return extracted_text

    except Exception as e:
        print(
            f"[PDF] pypdf failed: "
            f"{type(e).__name__}: {e}"
        )

    # ==========================================================
    # Strategy 2: pdfplumber
    # ==========================================================
    try:
        pages_text = []

        with pdfplumber.open(BytesIO(file_data)) as pdf:
            print(
                f"[PDF] pdfplumber opened PDF "
                f"with {len(pdf.pages)} page(s)"
            )

            for page_number, page in enumerate(pdf.pages, start=1):
                try:
                    page_text = page.extract_text() or ""

                    print(
                        f"[PDF] pdfplumber page {page_number}: "
                        f"{len(page_text)} characters"
                    )

                    if page_text.strip():
                        pages_text.append(page_text)

                except Exception as page_error:
                    print(
                        f"[PDF] pdfplumber page {page_number} failed: "
                        f"{type(page_error).__name__}: {page_error}"
                    )

        extracted_text = "\n".join(pages_text).strip()

        print(
            f"[PDF] pdfplumber extracted "
            f"{len(extracted_text)} characters"
        )

        if len(extracted_text) >= 50:
            return extracted_text

    except Exception as e:
        print(
            f"[PDF] pdfplumber failed: "
            f"{type(e).__name__}: {e}"
        )

    # ==========================================================
    # No usable text
    # ==========================================================
    raise ValueError(
        "Could not extract usable text from this PDF. "
        "The PDF may be scanned/image-only, corrupted, "
        "or password-protected. "
        "Please upload a PDF containing selectable text."
    )
    
def extract_text_from_docx(file_data: bytes) -> str:
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

        text = '\n'.join(text_parts)

        if not text.strip():
            raise FileParsingError(
                'No text could be extracted from the document. '
                'The document may be empty or corrupted.'
            )
        
        try:
            for rel in doc.part.rels.values():
                if 'hyperlink' in rel.reltype.lower():
                    url = rel._target
                    if isinstance(url, str) and url.startswith('http'):
                        text += '\n' + url
        except Exception:
            pass

        log_info(f'Extracted {len(text)} chars from DOCX', context='resume_parser')
        return text.strip()

    except FileParsingError:
        raise   # Re-raise unchanged — don't wrap in another FileParsingError

    except Exception as e:
        log_error(
            f"{type(e).__name__}: {e}",
            context='parse_resume_file_extraction'
        )
        raise

def extract_text_from_doc(file_data: bytes) -> str:
    raise FileParsingError(
        'Legacy .doc format is not supported. '
        'Please convert your document to .docx or .pdf and try again. '
        'You can convert using Microsoft Word, Google Docs, or online tools.'
    )

def extract_text(file_data: bytes, file_type: str) -> str:
    if file_type == 'pdf':
        return extract_text_from_pdf(file_data)
    elif file_type == 'docx':
        return extract_text_from_docx(file_data)
    elif file_type == 'doc':
        return extract_text_from_doc(file_data)
    elif file_type == 'txt':
        return file_data.decode('utf-8', errors='replace').strip()
    else:
        raise FileValidationError(
            f'Invalid file type: {file_type}. Supported types are: pdf, docx, txt, and doc.'
        )
    
def parse_resume_file(file_data: bytes, filename:str)->Tuple[str, dict]:
    log_info(f'parsing file :{filename}', context='parse_Resume_file')

    #phase01:validate file
    try:
        is_valid, error_msg, file_type=validate_file(file_data, filename)
        if not is_valid:
            log_warning(f'valiudation failed for file {filename}', context='parse_resume_file')
            raise FileValidationError(error_msg)
    
    except FileValidationError as e:
        raise 

    except Exception as e:
        log_error(e, context='parse_resume_file_validation')
        raise FileValidationError(
            'Could not validate the uploaded file. Please ensure it is a valid PDF or DOCX.'
        ) from e
    
    #phase02: extraction of file

    try:
        text = extract_text(file_data, file_type)
        log_info(f'Extracted {len(text)} chars from {filename}', context='parse_resume_file')

    except FileParsingError:
        raise   # Re-raise unchanged

    except Exception as e:
        import traceback

        print("\n========== RESUME PARSER ERROR ==========")
        print(f"Exception type: {type(e).__name__}")
        print(f"Exception message: {e}")
        traceback.print_exc()
        print("=========================================\n")

        log_error(e, context='parse_resume_file_extraction')

        raise FileParsingError(
            f'Failed to extract text from the resume: '
            f'{type(e).__name__}: {e}'
        ) from e

    metadata = {
        'filename':        filename,
        'file_type':       file_type,
        'file_size_bytes': len(file_data),
        'text_length':     len(text),
        'success':         True,
    }
    return text, metadata

def is_usable_text(text: str) -> bool:
    if not text:
        return False

    cleaned = " ".join(text.split())

    if len(cleaned) < 50:
        return False

    alphabetic = sum(ch.isalpha() for ch in cleaned)

    return alphabetic >= 30
