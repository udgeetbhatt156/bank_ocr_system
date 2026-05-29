"""
Dual OCR Engine Service
Handles both digital PDF extraction and PaddleOCR for scanned documents
"""
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pdfplumber
from bs4 import BeautifulSoup

LOGGER = logging.getLogger(__name__)

# Paddle/PaddleOCR 3.x can fail on some Windows CPU builds when the new PIR
# executor is enabled. Set these before importing paddleocr, then initialize the
# model lazily so app startup stays fast and digital PDFs do not pay OCR cost.
os.environ.setdefault("FLAGS_enable_pir_api", "false")
os.environ.setdefault("FLAGS_enable_pir_in_executor", "false")

paddle_ocr = None


def _get_paddle_ocr():
    global paddle_ocr
    if paddle_ocr is None:
        from paddleocr import PaddleOCR

        try:
            paddle_ocr = PaddleOCR(
                lang="en",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        except TypeError:
            # PaddleOCR 2.x compatibility.
            paddle_ocr = PaddleOCR(lang="en")
    return paddle_ocr


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


def _extract_text_from_v2_line(line: Any) -> Tuple[Optional[str], Optional[List], Optional[float]]:
    if not line or len(line) < 2:
        return None, None, None
    box = line[0]
    payload = line[1]
    if isinstance(payload, (list, tuple)):
        text = str(payload[0]) if payload else ""
        score = float(payload[1]) if len(payload) > 1 else None
    else:
        text = str(payload)
        score = None
    return text.strip() or None, box, score


def _result_to_dict(result: Any) -> Dict[str, Any]:
    if isinstance(result, dict):
        return result
    if hasattr(result, "json"):
        try:
            data = result.json
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    if hasattr(result, "to_dict"):
        try:
            data = result.to_dict()
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _box_center(box: Any) -> Tuple[float, float, float]:
    arr = np.array(box, dtype=float)
    if arr.ndim == 1 and arr.size >= 4:
        x0, y0, x1, y1 = arr[:4]
        return (x0 + x1) / 2, (y0 + y1) / 2, max(1.0, y1 - y0)
    if arr.ndim >= 2 and arr.shape[0] >= 2:
        xs = arr[:, 0]
        ys = arr[:, 1]
        return float(xs.mean()), float(ys.mean()), max(1.0, float(ys.max() - ys.min()))
    return 0.0, 0.0, 12.0


def _normalize_ocr_lines(result: Any) -> List[Dict[str, Any]]:
    lines: List[Dict[str, Any]] = []

    for page in result or []:
        data = _result_to_dict(page)
        if data:
            texts = data.get("rec_texts") or data.get("texts") or []
            scores = data.get("rec_scores") or data.get("scores") or []
            boxes = (
                data.get("rec_polys")
                or data.get("rec_boxes")
                or data.get("dt_polys")
                or data.get("boxes")
                or []
            )
            for idx, text in enumerate(texts):
                text = str(text).strip()
                if not text:
                    continue
                box = boxes[idx] if idx < len(boxes) else None
                score = scores[idx] if idx < len(scores) else None
                x, y, h = _box_center(box) if box is not None else (0.0, float(idx * 14), 12.0)
                lines.append({"text": text, "x": x, "y": y, "h": h, "score": score})
            continue

        # PaddleOCR 2.x shape: [[box, (text, score)], ...]
        page_lines = page if isinstance(page, list) else []
        for idx, line in enumerate(page_lines):
            text, box, score = _extract_text_from_v2_line(line)
            if not text:
                continue
            x, y, h = _box_center(box) if box is not None else (0.0, float(idx * 14), 12.0)
            lines.append({"text": text, "x": x, "y": y, "h": h, "score": score})

    return lines


def ocr_lines_to_rows(lines: List[Dict[str, Any]]) -> List[List[str]]:
    if not lines:
        return []

    sorted_lines = sorted(lines, key=lambda item: (item["y"], item["x"]))
    median_height = float(np.median([line["h"] for line in sorted_lines])) if sorted_lines else 12.0
    y_tolerance = max(8.0, median_height * 0.65)

    grouped: List[List[Dict[str, Any]]] = []
    for line in sorted_lines:
        if not grouped or abs(grouped[-1][0]["y"] - line["y"]) > y_tolerance:
            grouped.append([line])
        else:
            grouped[-1].append(line)

    header_anchor_idx = None
    header_anchors: List[Tuple[str, float]] = []
    for idx, group in enumerate(grouped):
        labels = [(item["text"].strip(), item["x"]) for item in sorted(group, key=lambda item: item["x"])]
        normalized = [re.sub(r"[^a-z]", "", text.lower()) for text, _ in labels]
        if "date" in normalized and "description" in normalized and (
            "additions" in normalized or "subtractions" in normalized
        ):
            header_anchor_idx = idx
            header_anchors = labels
            break

    rows: List[List[str]] = []
    for group_idx, group in enumerate(grouped):
        group = sorted(group, key=lambda item: item["x"])
        if (
            header_anchor_idx is not None
            and header_anchors
            and group_idx >= header_anchor_idx
        ):
            cells = _align_group_to_header(group, header_anchors)
        else:
            cells = [item["text"].strip() for item in group if item["text"].strip()]
        if cells:
            rows.append(cells)
    return rows


def _align_group_to_header(
    group: List[Dict[str, Any]], header_anchors: List[Tuple[str, float]]
) -> List[str]:
    cells = [""] * len(header_anchors)
    anchor_x = [x for _, x in header_anchors]

    for item in group:
        text = item["text"].strip()
        if not text:
            continue
        nearest_idx = min(
            range(len(anchor_x)),
            key=lambda idx: abs(float(item["x"]) - float(anchor_x[idx])),
        )
        if cells[nearest_idx]:
            cells[nearest_idx] = f"{cells[nearest_idx]} {text}"
        else:
            cells[nearest_idx] = text

    # Keep normal header labels exactly where OCR found them.
    return cells


def extract_ocr_rows(image: np.ndarray) -> List[List[str]]:
    """Run PaddleOCR and return geometry-preserving rows."""
    try:
        if image.ndim == 2:
            image = np.stack([image, image, image], axis=-1)
        ocr = _get_paddle_ocr()
        if hasattr(ocr, "predict"):
            result = ocr.predict(image)
        else:
            result = ocr.ocr(image, cls=True)
        return ocr_lines_to_rows(_normalize_ocr_lines(result))
    except Exception as e:
        LOGGER.error(f"Error in PaddleOCR: {e}")
        return []


def run_paddleocr_structure(image: np.ndarray) -> str:
    """
    Run PaddleOCR on preprocessed image
    
    Args:
        image: Preprocessed numpy array image
        
    Returns:
        Text extracted from image (simplified version)
    """
    try:
        rows = extract_ocr_rows(image)
        return '\n'.join(' '.join(row) for row in rows)
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
