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


def extract_text_from_image(file_path: Path) -> str:
    result = OCR_MODEL.ocr(str(file_path), cls=True)
    lines = []
    
    # PaddleOCR returns [page_results], where each page contains [[bbox, (text, confidence)], ...]
    for page_result in result:
        if not page_result:
            continue
        for record in page_result:
            if not record or len(record) < 2:
                continue
            bbox = record[0]
            content = record[1]
            
            # Extract text and confidence from content tuple
            if isinstance(content, (list, tuple)) and len(content) >= 2:
                text = content[0]
                confidence = content[1]
            elif isinstance(content, (list, tuple)) and content:
                text = content[0]
            else:
                text = str(content)
            
            # Get Y coordinate for sorting (top to bottom)
            y = bbox[0][1] if bbox and len(bbox) > 0 and len(bbox[0]) >= 2 else 0
            lines.append((y, _normalize_text(text)))

    lines.sort(key=lambda item: item[0])
    return "\n".join(line for _, line in lines if line)


def extract_text_from_pdf_ocr(file_path: Path) -> str:
    images = render_pdf_pages(file_path)
    print(images, "rendered images for OCR")
    try:
        page_texts = []
        for image_path in images:
            text = extract_text_from_image(image_path)
            if text:
                page_texts.append(text)
        return "\n\n".join(page_texts).strip()
    finally:
        for image_path in images:
            try:
                image_path.unlink()
            except Exception:
                LOGGER.warning("Unable to remove temporary image %s", image_path)
