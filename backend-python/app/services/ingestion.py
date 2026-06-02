from pathlib import Path
import fitz  # PyMuPDF
from typing import Tuple,Literal
 

from pathlib import Path
from typing import Literal


def detect_pdf_type(
    file_path: Path, 
    min_text_threshold: int = 120,      # Adjusted for bank statements
    min_pages_with_text: int = 2,
    total_chars_threshold: int = 700,
    image_heavy_threshold: float = 0.6   # New: ratio of image content
) -> Literal["digital", "scanned", "hybrid"]:
    """
    Detect PDF type: digital, scanned, or hybrid.
    Optimized for US bank statements (especially Washington Trust, etc.).
    """
    try:
        with fitz.open(file_path) as doc:
            if len(doc) == 0:
                return "scanned"

            total_text_chars = 0
            pages_with_text = 0
            total_images = 0
            max_pages_to_check = min(8, len(doc))

            for page_num in range(max_pages_to_check):
                page = doc[page_num]
                
                # Text analysis
                text = page.get_text("text").strip()
                text_length = len(text)
                total_text_chars += text_length
                
                if text_length > min_text_threshold:
                    pages_with_text += 1

                # Image analysis (important for hybrid detection)
                images = page.get_images(full=True)
                total_images += len(images)

                # Early detection
                if pages_with_text >= min_pages_with_text and total_text_chars > total_chars_threshold:
                    if len(images) > 3:   # Has significant images
                        return "hybrid"
                    return "digital"

            # Final decision logic
            has_good_text = pages_with_text >= min_pages_with_text or total_text_chars > total_chars_threshold
            has_images = total_images > 5 or (total_images / max(1, max_pages_to_check) > image_heavy_threshold)

            if has_good_text and has_images:
                return "hybrid"
            elif has_good_text:
                return "digital"
            elif total_text_chars > 400 and total_images == 0:
                return "digital"
            else:
                return "scanned"

          
            sample_text = doc.get_text()[:3000].lower()
            bank_keywords = ["account number", "statement date", "beginning balance", 
                           "ending balance", "activity in date order", "deposits", "withdrawals"]
            
            if any(kw in sample_text for kw in bank_keywords) and len(sample_text) > 400:
                if total_images > 8:
                    return "hybrid"
                return "digital"

    except Exception as e:
        print(f"PDF detection error for {file_path.name}: {e}")
        return "scanned"  # Safe fallback
    
# def detect_pdf_type(file_path: Path, min_text_threshold: int = 80) -> str:
#     """
#     Detect whether a bank statement PDF is 'digital' (text-based) or 'scanned' (image-based).
    
#     Returns: "digital" or "scanned"
#     """
#     try:
#         with fitz.open(file_path) as doc:
#             print(f"Analyzing PDF: {file_path} with {len(doc)} pages")
#             if len(doc) == 0:
#                 return "scanned"

#             total_text_chars = 0
#             pages_with_text = 0
#             pages_checked = 0
#             max_pages_to_check = min(5, len(doc))  # Optimize: check first few pages

#             for page_num in range(max_pages_to_check):
#                 page = doc[page_num]
#                 text = page.get_text("text").strip()
#                 text_length = len(text)

#                 total_text_chars += text_length
                
#                 # Count pages with meaningful text
#                 if text_length > min_text_threshold:
#                     pages_with_text += 1

#                 pages_checked += 1

#             # Decision logic
#             if pages_with_text >= 2 or total_text_chars > 500:
#                 return "digital"
            
#             # Additional check: text density on first page
#             if pages_checked > 0:
#                 avg_text_per_page = total_text_chars / pages_checked
#                 if avg_text_per_page > 150:
#                     return "digital"

#             # Fallback: Try to extract text from all pages if borderline
#             if total_text_chars < 300 and len(doc) > 3:
#                 full_text = doc.get_text().strip()
#                 if len(full_text) > 800:
#                     return "digital"

#             return "scanned"

#     except Exception as e:
#         # Log the error in production
#         print(f"PDF detection error for {file_path}: {e}")
#         return "scanned"  # Safe fallback
# from pathlib import Path
# import fitz


# def detect_pdf_type(file_path: Path) -> str:
#     """
#     Detect if PDF is digital or scanned.
#     """
#     try:
#         with fitz.open(file_path) as doc:
#             for page in doc:
#                 text = page.get_text()

#                 if len(text.strip()) > 100:
#                     return "digital"

#         return "scanned"

#     except Exception:
#         return "scanned"

# """
# PDF Type Detection Service
# Determines if a PDF is digital (text-extractable) or scanned (requires OCR).
# Designed for banking OCR pipelines using FastAPI + PaddleOCR.
# """

# import logging
# from dataclasses import dataclass, field
# from pathlib import Path
# from typing import Literal

# import fitz  # PyMuPDF

# logger = logging.getLogger(__name__)

# # --- Configuration Constants ---
# MIN_TEXT_CHARS_PER_PAGE = 50        # Minimum chars to consider a page "digital"
# DIGITAL_PAGE_RATIO_THRESHOLD = 0.6  # 60%+ digital pages → document is "digital"


# @dataclass
# class PageAnalysis:
#     """Analysis result for a single PDF page."""
#     page_number: int                          # 1-based
#     char_count: int
#     is_digital: bool
#     has_images: bool


# @dataclass
# class PDFTypeResult:
#     """Structured result for PDF type detection."""
#     file_path: str
#     doc_type: Literal["digital", "scanned", "hybrid", "unknown"]
#     total_pages: int
#     digital_pages: int
#     scanned_pages: int
#     digital_ratio: float                      # 0.0 → 1.0
#     page_details: list[PageAnalysis] = field(default_factory=list)
#     is_password_protected: bool = False
#     error: str | None = None

#     @property
#     def needs_ocr(self) -> bool:
#         """True if any page requires OCR processing."""
#         return self.doc_type in ("scanned", "hybrid")

#     @property
#     def ocr_page_numbers(self) -> list[int]:
#         """Returns 1-based page numbers that need OCR."""
#         return [p.page_number for p in self.page_details if not p.is_digital]


# def _validate_pdf_path(file_path: Path) -> str | None:
#     """
#     Validate file path before attempting to open.
#     Returns an error message string if invalid, else None.
#     """
#     if not file_path.exists():
#         return f"File not found: {file_path}"
#     if not file_path.is_file():
#         return f"Path is not a file: {file_path}"
#     if file_path.suffix.lower() != ".pdf":
#         return f"File is not a PDF (got '{file_path.suffix}'): {file_path}"
#     if file_path.stat().st_size == 0:
#         return f"File is empty (0 bytes): {file_path}"
#     return None


# def _analyse_page(page: fitz.Page, page_number: int) -> PageAnalysis:
#     """Extract digital/image signal from a single page."""
#     text = page.get_text() or ""
#     char_count = len(text.strip())
#     has_images = bool(page.get_images(full=False))
#     is_digital = char_count >= MIN_TEXT_CHARS_PER_PAGE

#     return PageAnalysis(
#         page_number=page_number,
#         char_count=char_count,
#         is_digital=is_digital,
#         has_images=has_images,
#     )


# def _determine_doc_type(
#     digital_pages: int,
#     scanned_pages: int,
#     total_pages: int,
# ) -> Literal["digital", "scanned", "hybrid", "unknown"]:
#     """
#     Classify overall document type based on page-level breakdown.

#     Rules:
#       - All pages digital            → "digital"
#       - All pages scanned            → "scanned"
#       - Mix of both                  → "hybrid"  (route to OCR for scanned pages)
#       - digital_ratio >= threshold   → "digital"
#       - No pages                     → "unknown"
#     """
#     if total_pages == 0:
#         return "unknown"
#     if digital_pages == total_pages:
#         return "digital"
#     if scanned_pages == total_pages:
#         return "scanned"

#     digital_ratio = digital_pages / total_pages
#     if digital_ratio >= DIGITAL_PAGE_RATIO_THRESHOLD:
#         return "digital"

#     return "hybrid"


# def detect_pdf_type(file_path: Path) -> PDFTypeResult:
#     """
#     Detect whether a bank statement PDF is digital, scanned, or hybrid.

#     - "digital"  → text is fully extractable; skip OCR
#     - "scanned"  → all pages need PaddleOCR
#     - "hybrid"   → mixed; OCR only the scanned pages (see result.ocr_page_numbers)
#     - "unknown"  → empty or unreadable document

#     Args:
#         file_path: Path to the PDF file.

#     Returns:
#         PDFTypeResult with full page-level breakdown and OCR routing info.
#     """
#     file_path = Path(file_path)  # Normalise in case a str is passed

#     # --- Step 1: Validate before opening ---
#     validation_error = _validate_pdf_path(file_path)
#     if validation_error:
#         logger.error("PDF validation failed: %s", validation_error)
#         return PDFTypeResult(
#             file_path=str(file_path),
#             doc_type="unknown",
#             total_pages=0,
#             digital_pages=0,
#             scanned_pages=0,
#             digital_ratio=0.0,
#             error=validation_error,
#         )

#     # --- Step 2: Open and analyse ---
#     try:
#         with fitz.open(file_path) as doc:

#             # Handle password-protected PDFs (common in bank statements)
#             if doc.needs_pass:
#                 logger.warning("PDF is password-protected: %s", file_path)
#                 return PDFTypeResult(
#                     file_path=str(file_path),
#                     doc_type="unknown",
#                     total_pages=0,
#                     digital_pages=0,
#                     scanned_pages=0,
#                     digital_ratio=0.0,
#                     is_password_protected=True,
#                     error="PDF is password-protected; cannot analyse without credentials.",
#                 )

#             total_pages = doc.page_count

#             # Handle empty PDFs
#             if total_pages == 0:
#                 logger.warning("PDF has no pages: %s", file_path)
#                 return PDFTypeResult(
#                     file_path=str(file_path),
#                     doc_type="unknown",
#                     total_pages=0,
#                     digital_pages=0,
#                     scanned_pages=0,
#                     digital_ratio=0.0,
#                     error="PDF contains no pages.",
#                 )

#             # --- Step 3: Page-level analysis ---
#             page_details: list[PageAnalysis] = []
#             for page_index, page in enumerate(doc, start=1):
#                 analysis = _analyse_page(page, page_number=page_index)
#                 page_details.append(analysis)
#                 logger.debug(
#                     "Page %d/%d → digital=%s, chars=%d, images=%s",
#                     page_index, total_pages,
#                     analysis.is_digital, analysis.char_count, analysis.has_images,
#                 )

#     except fitz.FileDataError as e:
#         logger.error("Corrupt or invalid PDF '%s': %s", file_path, e)
#         return PDFTypeResult(
#             file_path=str(file_path),
#             doc_type="unknown",
#             total_pages=0,
#             digital_pages=0,
#             scanned_pages=0,
#             digital_ratio=0.0,
#             error=f"Corrupt or invalid PDF: {e}",
#         )
#     except PermissionError as e:
#         logger.error("Permission denied reading '%s': %s", file_path, e)
#         return PDFTypeResult(
#             file_path=str(file_path),
#             doc_type="unknown",
#             total_pages=0,
#             digital_pages=0,
#             scanned_pages=0,
#             digital_ratio=0.0,
#             error=f"Permission denied: {e}",
#         )
#     except Exception as e:
#         # Catch-all — log with full traceback for unexpected failures
#         logger.exception("Unexpected error analysing PDF '%s': %s", file_path, e)
#         return PDFTypeResult(
#             file_path=str(file_path),
#             doc_type="unknown",
#             total_pages=0,
#             digital_pages=0,
#             scanned_pages=0,
#             digital_ratio=0.0,
#             error=f"Unexpected error: {e}",
#         )

#     # --- Step 4: Aggregate results ---
#     digital_pages = sum(1 for p in page_details if p.is_digital)
#     scanned_pages = total_pages - digital_pages
#     digital_ratio = digital_pages / total_pages if total_pages > 0 else 0.0
#     doc_type = _determine_doc_type(digital_pages, scanned_pages, total_pages)

#     logger.info(
#         "PDF '%s' → type=%s, pages=%d, digital=%d, scanned=%d, ratio=%.2f",
#         file_path.name, doc_type, total_pages, digital_pages, scanned_pages, digital_ratio,
#     )

#     return PDFTypeResult(
#         file_path=str(file_path),
#         doc_type=doc_type,
#         total_pages=total_pages,
#         digital_pages=digital_pages,
#         scanned_pages=scanned_pages,
#         digital_ratio=digital_ratio,
#         page_details=page_details,
#     )

# """
# PDF Type Detection Service
# Determines if a PDF is digital (text-extractable) or scanned (requires OCR)
# """
# import fitz  # PyMuPDF
# from pathlib import Path


