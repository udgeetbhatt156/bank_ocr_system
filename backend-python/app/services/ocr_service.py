import logging
import tempfile
from pathlib import Path
from typing import List

from paddleocr import PaddleOCR
from PIL import Image

from app.services.pdf_service import render_pdf_pages

LOGGER = logging.getLogger(__name__)
OCR_MODEL = PaddleOCR(use_angle_cls=True, lang="en", show_log=False, use_gpu=False)


def _normalize_text(text: str) -> str:
    return text.replace("\u3000", " ").replace("\xa0", " ").strip()


# def extract_text_from_image(file_path: Path) -> str:
#     result = OCR_MODEL.ocr(str(file_path), cls=True)
#     lines = []
    
#     # PaddleOCR returns [page_results], where each page contains [[bbox, (text, confidence)], ...]
#     for page_result in result:
#         if not page_result:
#             continue
#         for record in page_result:
#             if not record or len(record) < 2:
#                 continue
#             bbox = record[0]
#             content = record[1]
            
#             # Extract text and confidence from content tuple
#             if isinstance(content, (list, tuple)) and len(content) >= 2:
#                 text = content[0]
#                 confidence = content[1]
#             elif isinstance(content, (list, tuple)) and content:
#                 text = content[0]
#             else:
#                 text = str(content)
            
#             # Get Y coordinate for sorting (top to bottom)
#             y = bbox[0][1] if bbox and len(bbox) > 0 and len(bbox[0]) >= 2 else 0
#             lines.append((y, _normalize_text(text)))

#     lines.sort(key=lambda item: item[0])
#     return "\n".join(line for _, line in lines if line)


# def extract_text_from_pdf_ocr(file_path: Path) -> str:
#     images = render_pdf_pages(file_path)
#     print(images, "rendered images for OCR")
#     try:
#         page_texts = []
#         for image_path in images:
#             text = extract_text_from_image(image_path)
#             print(f"Extracted text from {image_path}: {text[:100]}...")  # Print first 100 chars for debugging
#             if text:
#                 page_texts.append(text)
#         return "\n\n".join(page_texts).strip()
#     finally:
#         for image_path in images:
#             try:
#                 image_path.unlink()
#             except Exception:
#                 LOGGER.warning("Unable to remove temporary image %s", image_path)

from pathlib import Path
import logging
from typing import List

LOGGER = logging.getLogger(__name__)

def extract_text_from_pdf_ocr(file_path: Path, dpi: int = 300) -> str:
    """
    Enhanced OCR extraction for US bank statements.
    """
    images = render_pdf_pages(file_path, dpi=dpi)  # Make sure this supports dpi
    print(f"Rendered {len(images)} images for OCR at {dpi} DPI")
    
    try:
        page_texts = []
        for i, image_path in enumerate(images):
            print(f"Processing page {i+1}/{len(images)}: {image_path}, {dpi} DPI")
            
            # Enhanced OCR with preprocessing suggestions
            text = extract_text_from_image(
                image_path,
                preprocess=True,           # Add this if your function supports it
                config='--psm 6'           # Assume uniform block of text (good for statements)
            )
            
            if text:
                print(f"Raw extracted text from page {i+1} (first 100 chars): {text[:100]}...")
                cleaned = clean_ocr_text(text)
                page_texts.append(cleaned)
                print(f"Page {i+1} extracted length: {len(cleaned)} chars")
            else:
                print(f"Warning: No text extracted from page {i+1}")
                
        full_text = "\n\n".join(page_texts).strip()
        print(f"Total extracted text length: {len(full_text)} characters")
        
        return full_text
        
    finally:
        # Cleanup
        for image_path in images:
            try:
                image_path.unlink(missing_ok=True)
            except Exception as e:
                LOGGER.warning(f"Failed to delete temp image {image_path}: {e}")


def clean_ocr_text(text: str) -> str:
    """Clean common OCR artifacts from bank statements."""
    import re
    
    # Fix common issues
    text = re.sub(r'\s+', ' ', text)                    # Normalize whitespace
    text = re.sub(r'(\d),(\d{3})', r'\1\2', text)      # Fix comma in numbers like 1,234
    text = re.sub(r'O(\d)', r'0\1', text)               # Fix O mistaken for 0
    text = re.sub(r'(\d)I(\d)', r'\1 1 \2', text)       # Fix I mistaken for 1
    text = re.sub(r'(\d)B(\d)', r'\1 8 \2', text)       # B -> 8
    
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if line and len(line) > 3:                      # Remove very short noise
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)