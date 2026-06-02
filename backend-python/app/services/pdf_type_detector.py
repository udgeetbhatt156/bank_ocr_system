from pathlib import Path
from typing import Literal

import fitz  # PyMuPDF


def detect_pdf_type(
    file_path: Path,
    min_text_threshold: int = 120,
    min_pages_with_text: int = 2,
    total_chars_threshold: int = 700,
    image_heavy_threshold: float = 0.6,
) -> Literal["digital", "scanned", "hybrid"]:
    """Detect whether the PDF is digital, scanned, or hybrid."""
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
                text = page.get_text("text").strip()
                text_length = len(text)
                total_text_chars += text_length

                if text_length > min_text_threshold:
                    pages_with_text += 1

                images = page.get_images(full=True)
                total_images += len(images)

                if pages_with_text >= min_pages_with_text and total_text_chars > total_chars_threshold:
                    if len(images) > 3:
                        return "hybrid"
                    return "digital"

            has_good_text = pages_with_text >= min_pages_with_text or total_text_chars > total_chars_threshold
            has_images = total_images > 5 or (total_images / max(1, max_pages_to_check) > image_heavy_threshold)

            if has_good_text and has_images:
                return "hybrid"
            elif has_good_text:
                return "digital"
            elif total_text_chars > 400 and total_images == 0:
                return "digital"
            return "scanned"

    except Exception as e:
        print(f"PDF detection error for {file_path.name}: {e}")
        return "scanned"
