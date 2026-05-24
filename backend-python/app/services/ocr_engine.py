"""
Dual OCR Engine Service
Handles both digital PDF extraction and PaddleOCR for scanned documents
"""
import logging
from pathlib import Path
from typing import List, Optional
import numpy as np
import pdfplumber
from paddleocr import PaddleOCR
from bs4 import BeautifulSoup

LOGGER = logging.getLogger(__name__)

# Initialize PaddleOCR for OCR
# Using minimal parameters for compatibility
paddle_ocr = PaddleOCR(lang='en')


def extract_digital_pdf(file_path: Path) -> List[List[str]]:
    """
    Extract tables from digital PDFs using pdfplumber
    
    Args:
        file_path: Path to PDF file
        
    Returns:
        List of rows (each row is a list of cell values)
    """
    all_rows = []
    
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                # Try to extract tables first
                tables = page.extract_tables()
                
                if tables:
                    for table in tables:
                        for row in table:
                            if row and any(cell for cell in row if cell):
                                # Clean cells
                                cleaned_row = [
                                    str(cell).strip() if cell else "" 
                                    for cell in row
                                ]
                                all_rows.append(cleaned_row)
                else:
                    # Fallback to text extraction
                    text = page.extract_text()
                    if text:
                        lines = text.split('\n')
                        for line in lines:
                            if line.strip():
                                # Split by multiple spaces (common in statements)
                                parts = [p.strip() for p in line.split('  ') if p.strip()]
                                if parts:
                                    all_rows.append(parts)
    except Exception as e:
        LOGGER.error(f"Error extracting digital PDF: {e}")
        raise
    
    return all_rows


def run_paddleocr_structure(image: np.ndarray) -> str:
    """
    Run PaddleOCR on preprocessed image
    
    Args:
        image: Preprocessed numpy array image
        
    Returns:
        Text extracted from image (simplified version)
    """
    try:
        result = paddle_ocr.ocr(image, cls=True)
        
        # Extract text from OCR result
        lines = []
        if result and result[0]:
            for line in result[0]:
                if line and len(line) >= 2:
                    text = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                    lines.append(text)
        
        return '\n'.join(lines)
    
    except Exception as e:
        LOGGER.error(f"Error in PaddleOCR: {e}")
        return ""


def parse_ocr_text_to_rows(text: str) -> List[List[str]]:
    """
    Parse OCR text to list of rows
    
    Args:
        text: Plain text from PaddleOCR
        
    Returns:
        List of rows (each row is a list of cell values)
    """
    if not text:
        return []
    
    try:
        rows = []
        for line in text.split('\n'):
            if line.strip():
                # Split by multiple spaces (common in statements)
                cells = [cell.strip() for cell in line.split('  ') if cell.strip()]
                if not cells:
                    # Fallback: split by single space if no double spaces
                    cells = [cell.strip() for cell in line.split() if cell.strip()]
                if cells:
                    rows.append(cells)
        
        return rows
    
    except Exception as e:
        LOGGER.error(f"Error parsing OCR text: {e}")
        return []
