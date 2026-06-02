from pathlib import Path
from typing import List
import tempfile

import pdfplumber
import fitz


def tables_to_text(tables: List[List[List[str]]]) -> str:
    rows: List[str] = []
    for table in tables:
        for row in table:
            cleaned = [cell.strip() if cell else "" for cell in row]
            if any(cleaned):
                rows.append("  ".join(cleaned))
    return "\n".join(rows)


def extract_text_from_pdf(file_path: Path) -> str:
    text_pages: List[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                text_pages.append(text)
                continue

            tables = page.extract_tables()
            if tables:
                text_pages.append(tables_to_text(tables))
    return "\n\n".join(text_pages).strip()


def is_digital_pdf(file_path: Path) -> bool:
    try:
        text = extract_text_from_pdf(file_path)
        return len(text) > 80
    except Exception:
        return False


def render_pdf_pages(file_path: Path, dpi: int = 200) -> List[Path]:
    output_images: List[Path] = []
    temp_dir = Path(tempfile.mkdtemp())

    with fitz.open(file_path) as document:
        for page_number, page in enumerate(document, start=1):
            pix = page.get_pixmap(alpha=False, dpi=dpi)
            image_path = temp_dir / f"{file_path.stem}_page_{page_number}.png"
            pix.save(str(image_path))
            output_images.append(image_path)
    return output_images
