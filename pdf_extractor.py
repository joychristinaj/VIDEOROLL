"""
PDF text extraction service using PyMuPDF (fitz).
Falls back to OCR via pytesseract when scanned pages are detected.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import List, Tuple

from app.models.schemas import PageText, PDFExtractResponse

# Optional Tesseract support
_tesseract_available: bool = False
try:
    import pytesseract
    from PIL import Image
    _tesseract_available = True
except ImportError:
    pass

# PyMuPDF and pypdf
_fitz_available: bool = False
try:
    import fitz  # PyMuPDF
    # Quick probe to ensure C DLLs are loaded properly
    _doc = fitz.open()
    _doc.close()
    _fitz_available = True
except Exception:
    _fitz_available = False

_pypdf_available: bool = False
try:
    import pypdf
    _pypdf_available = True
except ImportError:
    pass

HEADING_PATTERNS = [
    re.compile(r"^#{1,6}\s+(.+)"),          # Markdown headings
    re.compile(r"^([A-Z][A-Z\s]{2,60})$"),  # ALL-CAPS lines
    re.compile(r"^(\d+\.\s+[A-Z].{3,60})$"),# Numbered headings
]

MIN_TEXT_CHARS_PER_PAGE = 30  # Below this -> likely scanned


def _extract_headings(text: str) -> List[str]:
    headings = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for pat in HEADING_PATTERNS:
            m = pat.match(line)
            if m:
                headings.append(m.group(1).strip())
                break
    return headings


def _is_page_scanned(text: str) -> bool:
    """Return True when the page has very little extractable text."""
    return len(text.strip()) < MIN_TEXT_CHARS_PER_PAGE


def extract_pdf(
    file_bytes: bytes,
    filename: str,
    max_pages: int = 200,
    use_ocr: bool = False,
) -> PDFExtractResponse:
    """
    Extract text from a PDF file.

    Raises ValueError for invalid, encrypted, or unsupported PDFs.
    """
    if not _fitz_available and not _pypdf_available:
        raise RuntimeError(
            "Neither PyMuPDF (fitz) nor pypdf is installed/working. Run: pip install pypdf"
        )

    if _fitz_available:
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as exc:
            raise ValueError(f"Could not open PDF – file may be corrupted: {exc}") from exc

        if doc.is_encrypted:
            doc.close()
            raise ValueError(
                "This PDF is password-protected. Please provide an unlocked version."
            )

        page_count = doc.page_count
        if page_count == 0:
            doc.close()
            raise ValueError("The PDF appears to be empty (0 pages).")

        if page_count > max_pages:
            doc.close()
            raise ValueError(
                f"PDF has {page_count} pages, which exceeds the limit of {max_pages}."
            )

        pages: List[PageText] = []
        ocr_used = False
        warnings: List[str] = []
        scanned_pages: List[int] = []

        for i, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            if _is_page_scanned(text):
                scanned_pages.append(i)
                if use_ocr and _tesseract_available:
                    try:
                        pix = page.get_pixmap(dpi=150)
                        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                        text = pytesseract.image_to_string(img)
                        ocr_used = True
                    except Exception as exc:
                        warnings.append(f"OCR failed on page {i}: {exc}")
                        text = ""
                else:
                    text = ""

            headings = _extract_headings(text)
            pages.append(PageText(page_number=i, text=text.strip(), headings=headings))

        doc.close()
    else:
        # Fallback to pypdf
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        except Exception as exc:
            raise ValueError(f"Could not open PDF – file may be corrupted: {exc}") from exc

        if reader.is_encrypted:
            raise ValueError(
                "This PDF is password-protected. Please provide an unlocked version."
            )

        page_count = len(reader.pages)
        if page_count == 0:
            raise ValueError("The PDF appears to be empty (0 pages).")

        if page_count > max_pages:
            raise ValueError(
                f"PDF has {page_count} pages, which exceeds the limit of {max_pages}."
            )

        pages: List[PageText] = []
        ocr_used = False
        warnings: List[str] = []
        scanned_pages: List[int] = []

        for i, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""

            if _is_page_scanned(text):
                scanned_pages.append(i)
                # Note: Pure pypdf does not render pixmaps for OCR directly
                text = ""

            headings = _extract_headings(text)
            pages.append(PageText(page_number=i, text=text.strip(), headings=headings))

    if scanned_pages and not ocr_used:
        if _tesseract_available:
            warnings.append(
                f"Pages {scanned_pages[:5]} appear to be scanned images. "
                "Enable OCR to extract their text."
            )
        else:
            warnings.append(
                f"Pages {scanned_pages[:5]} appear to be scanned images. "
                "Tesseract OCR is not installed; text cannot be extracted from these pages. "
                "Install tesseract and pytesseract to enable OCR."
            )

    full_text = "\n\n".join(
        f"[Page {p.page_number}]\n{p.text}" for p in pages if p.text
    )

    if not full_text.strip():
        raise ValueError(
            "No readable text could be extracted from this PDF. "
            "The document may consist entirely of scanned images. "
            + ("Install Tesseract OCR to process scanned PDFs." if not _tesseract_available else "")
        )

    return PDFExtractResponse(
        filename=filename,
        page_count=page_count,
        pages=pages,
        full_text=full_text,
        ocr_used=ocr_used,
        ocr_available=_tesseract_available,
        warnings=warnings,
    )


def validate_pdf_bytes(data: bytes) -> None:
    """
    Validate PDF file signature (%PDF-).
    Raises ValueError if the file is not a valid PDF.
    """
    if not data.startswith(b"%PDF-"):
        raise ValueError(
            "The uploaded file does not appear to be a valid PDF "
            "(missing %PDF- header signature)."
        )
