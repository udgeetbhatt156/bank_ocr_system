from pathlib import Path
import re
from typing import List

import pdfplumber


def extract_digital_pdf(file_path: Path) -> List[List[str]]:
    """Extract rows from a digital PDF using pdfplumber."""
    all_rows: List[List[str]] = []

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_width = page.width or 612

            tables = page.extract_tables()
            if not tables:
                tables = page.extract_tables({
                    "vertical_strategy": "text",
                    "horizontal_strategy": "text",
                    "min_words_vertical": 3,
                    "min_words_horizontal": 1,
                })
            if tables:
                for table in tables:
                    for row in table:
                        cleaned = [str(c).strip() if c else "" for c in row]
                        if any(cleaned):
                            all_rows.append(cleaned)
                continue

            words = page.extract_words(
                x_tolerance=5,
                y_tolerance=5,
                keep_blank_chars=False,
                use_text_flow=False,
            )
            if not words:
                text = page.extract_text() or ""
                for line in text.splitlines():
                    parts = [p.strip() for p in re.split(r'\s{2,}', line) if p.strip()]
                    if parts:
                        all_rows.append(parts)
                continue

            heights = [w.get('height', w['bottom'] - w['top']) for w in words]
            median_h = sorted(heights)[len(heights) // 2] if heights else 12
            y_tol = max(4, median_h * 0.5)

            lines = {}
            for w in words:
                y_key = round(w['top'] / y_tol) * y_tol
                lines.setdefault(y_key, []).append(w)

            col_gap = max(12, page_width * 0.02)

            for y_key in sorted(lines):
                line_words = sorted(lines[y_key], key=lambda w: w['x0'])
                cols = []
                current = line_words[0]['text']
                for prev, curr in zip(line_words, line_words[1:]):
                    gap = curr['x0'] - prev['x1']
                    if gap > col_gap:
                        cols.append(current.strip())
                        current = curr['text']
                    else:
                        current += ' ' + curr['text']
                cols.append(current.strip())
                if any(cols):
                    all_rows.append(cols)

    return all_rows


# Backward compatibility
extract_with_pdfplumber = extract_digital_pdf
