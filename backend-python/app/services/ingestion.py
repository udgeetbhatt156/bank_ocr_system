"""
PDF Type Detection Service
Determines if a PDF is digital (text-extractable) or scanned (requires OCR).
Designed for banking OCR pipelines using FastAPI + PaddleOCR.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# --- Configuration Constants ---
MIN_TEXT_CHARS_PER_PAGE = 50        # Minimum chars to consider a page "digital"
DIGITAL_PAGE_RATIO_THRESHOLD = 0.6  # 60%+ digital pages → document is "digital"


@dataclass
class PageAnalysis:
    """Analysis result for a single PDF page."""
    page_number: int                          # 1-based
    char_count: int
    is_digital: bool
    has_images: bool


@dataclass
class PDFTypeResult:
    """Structured result for PDF type detection."""
    file_path: str
    doc_type: Literal["digital", "scanned", "hybrid", "unknown"]
    total_pages: int
    digital_pages: int
    scanned_pages: int
    digital_ratio: float                      # 0.0 → 1.0
    page_details: list[PageAnalysis] = field(default_factory=list)
    is_password_protected: bool = False
    error: str | None = None

    @property
    def needs_ocr(self) -> bool:
        """True if any page requires OCR processing."""
        return self.doc_type in ("scanned", "hybrid")

    @property
    def ocr_page_numbers(self) -> list[int]:
        """Returns 1-based page numbers that need OCR."""
        return [p.page_number for p in self.page_details if not p.is_digital]


def _validate_pdf_path(file_path: Path) -> str | None:
    """
    Validate file path before attempting to open.
    Returns an error message string if invalid, else None.
    """
    if not file_path.exists():
        return f"File not found: {file_path}"
    if not file_path.is_file():
        return f"Path is not a file: {file_path}"
    if file_path.suffix.lower() != ".pdf":
        return f"File is not a PDF (got '{file_path.suffix}'): {file_path}"
    if file_path.stat().st_size == 0:
        return f"File is empty (0 bytes): {file_path}"
    return None


def _analyse_page(page: fitz.Page, page_number: int) -> PageAnalysis:
    """Extract digital/image signal from a single page."""
    text = page.get_text() or ""
    char_count = len(text.strip())
    has_images = bool(page.get_images(full=False))
    is_digital = char_count >= MIN_TEXT_CHARS_PER_PAGE

    return PageAnalysis(
        page_number=page_number,
        char_count=char_count,
        is_digital=is_digital,
        has_images=has_images,
    )


def _determine_doc_type(
    digital_pages: int,
    scanned_pages: int,
    total_pages: int,
) -> Literal["digital", "scanned", "hybrid", "unknown"]:
    """
    Classify overall document type based on page-level breakdown.

    Rules:
      - All pages digital            → "digital"
      - All pages scanned            → "scanned"
      - Mix of both                  → "hybrid"  (route to OCR for scanned pages)
      - digital_ratio >= threshold   → "digital"
      - No pages                     → "unknown"
    """
    if total_pages == 0:
        return "unknown"
    if digital_pages == total_pages:
        return "digital"
    if scanned_pages == total_pages:
        return "scanned"

    digital_ratio = digital_pages / total_pages
    if digital_ratio >= DIGITAL_PAGE_RATIO_THRESHOLD:
        return "digital"

    return "hybrid"


def detect_pdf_type(file_path: Path) -> PDFTypeResult:
    """
    Detect whether a bank statement PDF is digital, scanned, or hybrid.

    - "digital"  → text is fully extractable; skip OCR
    - "scanned"  → all pages need PaddleOCR
    - "hybrid"   → mixed; OCR only the scanned pages (see result.ocr_page_numbers)
    - "unknown"  → empty or unreadable document

    Args:
        file_path: Path to the PDF file.

    Returns:
        PDFTypeResult with full page-level breakdown and OCR routing info.
    """
    file_path = Path(file_path)  # Normalise in case a str is passed

    # --- Step 1: Validate before opening ---
    validation_error = _validate_pdf_path(file_path)
    if validation_error:
        logger.error("PDF validation failed: %s", validation_error)
        return PDFTypeResult(
            file_path=str(file_path),
            doc_type="unknown",
            total_pages=0,
            digital_pages=0,
            scanned_pages=0,
            digital_ratio=0.0,
            error=validation_error,
        )

    # --- Step 2: Open and analyse ---
    try:
        with fitz.open(file_path) as doc:

            # Handle password-protected PDFs (common in bank statements)
            if doc.needs_pass:
                logger.warning("PDF is password-protected: %s", file_path)
                return PDFTypeResult(
                    file_path=str(file_path),
                    doc_type="unknown",
                    total_pages=0,
                    digital_pages=0,
                    scanned_pages=0,
                    digital_ratio=0.0,
                    is_password_protected=True,
                    error="PDF is password-protected; cannot analyse without credentials.",
                )

            total_pages = doc.page_count

            # Handle empty PDFs
            if total_pages == 0:
                logger.warning("PDF has no pages: %s", file_path)
                return PDFTypeResult(
                    file_path=str(file_path),
                    doc_type="unknown",
                    total_pages=0,
                    digital_pages=0,
                    scanned_pages=0,
                    digital_ratio=0.0,
                    error="PDF contains no pages.",
                )

            # --- Step 3: Page-level analysis ---
            page_details: list[PageAnalysis] = []
            for page_index, page in enumerate(doc, start=1):
                analysis = _analyse_page(page, page_number=page_index)
                page_details.append(analysis)
                logger.debug(
                    "Page %d/%d → digital=%s, chars=%d, images=%s",
                    page_index, total_pages,
                    analysis.is_digital, analysis.char_count, analysis.has_images,
                )

    except fitz.FileDataError as e:
        logger.error("Corrupt or invalid PDF '%s': %s", file_path, e)
        return PDFTypeResult(
            file_path=str(file_path),
            doc_type="unknown",
            total_pages=0,
            digital_pages=0,
            scanned_pages=0,
            digital_ratio=0.0,
            error=f"Corrupt or invalid PDF: {e}",
        )
    except PermissionError as e:
        logger.error("Permission denied reading '%s': %s", file_path, e)
        return PDFTypeResult(
            file_path=str(file_path),
            doc_type="unknown",
            total_pages=0,
            digital_pages=0,
            scanned_pages=0,
            digital_ratio=0.0,
            error=f"Permission denied: {e}",
        )
    except Exception as e:
        # Catch-all — log with full traceback for unexpected failures
        logger.exception("Unexpected error analysing PDF '%s': %s", file_path, e)
        return PDFTypeResult(
            file_path=str(file_path),
            doc_type="unknown",
            total_pages=0,
            digital_pages=0,
            scanned_pages=0,
            digital_ratio=0.0,
            error=f"Unexpected error: {e}",
        )

    # --- Step 4: Aggregate results ---
    digital_pages = sum(1 for p in page_details if p.is_digital)
    scanned_pages = total_pages - digital_pages
    digital_ratio = digital_pages / total_pages if total_pages > 0 else 0.0
    doc_type = _determine_doc_type(digital_pages, scanned_pages, total_pages)

    logger.info(
        "PDF '%s' → type=%s, pages=%d, digital=%d, scanned=%d, ratio=%.2f",
        file_path.name, doc_type, total_pages, digital_pages, scanned_pages, digital_ratio,
    )

    return PDFTypeResult(
        file_path=str(file_path),
        doc_type=doc_type,
        total_pages=total_pages,
        digital_pages=digital_pages,
        scanned_pages=scanned_pages,
        digital_ratio=digital_ratio,
        page_details=page_details,
    )

# """
# PDF Type Detection Service
# Determines if a PDF is digital (text-extractable) or scanned (requires OCR)
# """
# import fitz  # PyMuPDF
# from pathlib import Path


# def detect_pdf_type(file_path: Path) -> str:
#     """
#     Detect if PDF is digital or scanned.
    
#     Args:
#         file_path: Path to PDF file
        
#     Returns:
#         "digital" if text is extractable, "scanned" if OCR is needed
#     """
#     try:
#         with fitz.open(file_path) as doc:
#             for page in doc:
#                 text = page.get_text()
#                 # If any page has >100 extractable characters, it's digital
#                 if len(text.strip()) > 100:
#                     return "digital"
#         return "scanned"
#     except Exception:
#         # If we can't open it, assume scanned
#         return "scanned"
# print(detect_pdf_type,"Type of Pdf bro")