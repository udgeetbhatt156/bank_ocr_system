from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

import pdfplumber


def normalize_extracted_cell(value: str) -> str:
    """
    Clean common digital-PDF extraction artifacts without touching numbers.

    Some statement PDFs emit repeated glyphs such as TTTToooottttaaaallll and
    $$$$99990000....00000000. Collapsing non-digit runs keeps real amounts from
    losing digits while making headers/parser keywords usable again.
    """
    value = re.sub(r'([A-Za-z$.,:/#])\1{2,}', r'\1', value)
    return re.sub(r'\s+', ' ', value).strip()


def _row_text(row: List[str]) -> str:
    return " ".join(str(cell or "") for cell in row).lower()


def _looks_like_transaction_table(rows: List[List[str]]) -> bool:
    """Accept pdfplumber tables only when they contain transaction structure."""
    if not rows:
        return False

    joined = "\n".join(_row_text(row) for row in rows[:30])
    has_date = bool(re.search(r"\b(date|posted|transaction date)\b", joined))
    has_detail = bool(
        re.search(r"\b(description|detail|details|transaction|activity|amount)\b", joined)
    )
    has_amount = bool(
        re.search(r"\b(amount|debit|credit|withdrawal|deposit|balance)\b", joined)
    )
    data_like_rows = sum(
        1
        for row in rows
        if re.search(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", _row_text(row))
        and re.search(r"\(?\$?\s*\d[\d,]*\.\d{2}-?\)?", _row_text(row))
    )

    return (has_date and has_detail and has_amount) or data_like_rows >= 3


def _extract_rows_from_words(page) -> List[List[str]]:
    page_width = page.width or 612
    words = page.extract_words(
        x_tolerance=5,
        y_tolerance=5,
        keep_blank_chars=False,
        use_text_flow=False,
    )
    if not words:
        text = page.extract_text() or ""
        rows: List[List[str]] = []
        for line in text.splitlines():
            parts = [
                normalize_extracted_cell(p)
                for p in re.split(r'\s{2,}', line)
                if p.strip()
            ]
            if parts:
                rows.append(parts)
        return rows

    heights = [w.get('height', w['bottom'] - w['top']) for w in words]
    median_h = sorted(heights)[len(heights) // 2] if heights else 12
    y_tol = max(4, median_h * 0.5)

    lines = {}
    for w in words:
        y_key = round(w['top'] / y_tol) * y_tol
        lines.setdefault(y_key, []).append(w)

    col_gap = max(12, page_width * 0.02)
    rows: List[List[str]] = []

    for y_key in sorted(lines):
        line_words = sorted(lines[y_key], key=lambda w: w['x0'])
        cols = []
        current = line_words[0]['text']
        for prev, curr in zip(line_words, line_words[1:]):
            gap = curr['x0'] - prev['x1']
            if gap > col_gap:
                cols.append(normalize_extracted_cell(current))
                current = curr['text']
            else:
                current += ' ' + curr['text']
        cols.append(normalize_extracted_cell(current))
        if any(cols):
            rows.append(cols)
    return rows


def _word_bbox(word: Dict[str, Any]) -> Dict[str, Optional[float]]:
    return {
        "x0": word.get("x0"),
        "top": word.get("top"),
        "x1": word.get("x1"),
        "bottom": word.get("bottom"),
    }


def _merge_bbox(words: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    if not words:
        return {"x0": None, "top": None, "x1": None, "bottom": None}
    return {
        "x0": min(float(w["x0"]) for w in words if "x0" in w),
        "top": min(float(w["top"]) for w in words if "top" in w),
        "x1": max(float(w["x1"]) for w in words if "x1" in w),
        "bottom": max(float(w["bottom"]) for w in words if "bottom" in w),
    }


def _group_words_for_debug(page) -> List[Dict[str, Any]]:
    page_width = page.width or 612
    words = page.extract_words(
        x_tolerance=5,
        y_tolerance=5,
        keep_blank_chars=False,
        use_text_flow=False,
    )
    if not words:
        return []

    heights = [w.get("height", w["bottom"] - w["top"]) for w in words]
    median_h = sorted(heights)[len(heights) // 2] if heights else 12
    y_tol = max(4, median_h * 0.5)
    col_gap = max(12, page_width * 0.02)

    lines: Dict[float, List[Dict[str, Any]]] = {}
    for word in words:
        y_key = round(word["top"] / y_tol) * y_tol
        lines.setdefault(y_key, []).append(word)

    debug_rows: List[Dict[str, Any]] = []
    for row_index, y_key in enumerate(sorted(lines)):
        line_words = sorted(lines[y_key], key=lambda item: item["x0"])
        cells: List[Dict[str, Any]] = []
        current_words = [line_words[0]]

        for prev, curr in zip(line_words, line_words[1:]):
            if curr["x0"] - prev["x1"] > col_gap:
                text = normalize_extracted_cell(
                    " ".join(str(w.get("text", "")) for w in current_words)
                )
                cells.append({
                    "cell_index": len(cells),
                    "text": text,
                    **_merge_bbox(current_words),
                })
                current_words = [curr]
            else:
                current_words.append(curr)

        text = normalize_extracted_cell(
            " ".join(str(w.get("text", "")) for w in current_words)
        )
        cells.append({
            "cell_index": len(cells),
            "text": text,
            **_merge_bbox(current_words),
        })

        row_box = _merge_bbox(line_words)
        debug_rows.append({
            "row_index": row_index,
            "text": " | ".join(cell["text"] for cell in cells if cell["text"]),
            "cells": cells,
            **row_box,
        })

    return debug_rows


def compile_digital_extraction_debug(
    file_path: Path,
    *,
    max_pages: int = 25,
    max_words_per_page: int = 1500,
) -> Dict[str, Any]:
    """
    Compile raw pdfplumber word/cell coordinates before any column mapping.

    Coordinates are in PDF page points with origin at the top-left, matching
    pdfplumber's x0/top/x1/bottom convention.
    """
    pages: List[Dict[str, Any]] = []

    with pdfplumber.open(file_path) as pdf:
        for page_index, page in enumerate(pdf.pages[:max_pages], start=1):
            words = page.extract_words(
                x_tolerance=5,
                y_tolerance=5,
                keep_blank_chars=False,
                use_text_flow=False,
            )
            debug_words = []
            for word_index, word in enumerate(words[:max_words_per_page]):
                debug_words.append({
                    "word_index": word_index,
                    "text": normalize_extracted_cell(str(word.get("text", ""))),
                    **_word_bbox(word),
                })

            rows = _group_words_for_debug(page)
            pages.append({
                "page_number": page_index,
                "width": page.width,
                "height": page.height,
                "word_count": len(words),
                "words_truncated": len(words) > max_words_per_page,
                "words": debug_words,
                "rows": rows,
            })

    return {
        "source": "pdfplumber_words",
        "coordinate_system": "pdf_points_top_left",
        "pages": pages,
        "page_count": len(pages),
        "row_count": sum(len(page["rows"]) for page in pages),
        "cell_count": sum(
            len(row["cells"]) for page in pages for row in page["rows"]
        ),
    }


def extract_digital_pdf(file_path: Path) -> List[List[str]]:
    """Extract rows from a digital PDF using pdfplumber."""
    all_rows: List[List[str]] = []

    with pdfplumber.open(file_path) as pdf:
        # Check if the document is an Indiana Members Credit Union (IMCU) statement
        is_imcu = False
        if len(pdf.pages) > 0:
            first_page_text = pdf.pages[0].extract_text() or ""
            if any(kw in first_page_text.lower() for kw in ["indiana members", "imcu", "keeping it simple"]):
                is_imcu = True

        for page in pdf.pages:
            page_rows: List[List[str]] = []
            
            # If not IMCU, attempt table extraction first
            if not is_imcu:
                tables = page.extract_tables()
                if not tables:
                    tables = page.extract_tables({
                        "vertical_strategy": "text",
                        "horizontal_strategy": "text",
                        "min_words_vertical": 3,
                        "min_words_horizontal": 1,
                    })
                if tables:
                    table_rows: List[List[str]] = []
                    for table in tables:
                        for row in table:
                            cleaned = [
                                normalize_extracted_cell(str(c)) if c else ""
                                for c in row
                            ]
                            if any(cleaned):
                                table_rows.append(cleaned)
                    if _looks_like_transaction_table(table_rows):
                        page_rows = table_rows

            if not page_rows:
                page_rows = _extract_rows_from_words(page)

            all_rows.extend(page_rows)

    return all_rows


# Backward compatibility
extract_with_pdfplumber = extract_digital_pdf
