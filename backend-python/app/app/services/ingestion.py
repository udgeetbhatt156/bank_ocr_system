"""
PDF Type Detection Service
Determines if a PDF is digital (text-extractable) or scanned (requires OCR)
"""
import fitz  # PyMuPDF
from pathlib import Path


def detect_pdf_type(file_path: Path) -> str:
    """
    Detect if PDF is digital or scanned.
    
    Args:
        file_path: Path to PDF file
        
    Returns:
        "digital" if text is extractable, "scanned" if OCR is needed
    """
    try:
        with fitz.open(file_path) as doc:
            for page in doc:
                text = page.get_text()
                # If any page has >100 extractable characters, it's digital
                if len(text.strip()) > 100:
                    return "digital"
        return "scanned"
    except Exception:
        # If we can't open it, assume scanned
        return "scanned"
