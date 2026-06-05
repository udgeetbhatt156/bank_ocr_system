import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

LOGGER = logging.getLogger(__name__)

os.environ.setdefault("FLAGS_enable_pir_api", "false")
os.environ.setdefault("FLAGS_enable_pir_in_executor", "false")

paddle_ocr = None


def _get_paddle_ocr():
    global paddle_ocr
    if paddle_ocr is None:
        from paddleocr import PaddleOCR

        attempts = [
            {
                "lang": "en",
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "use_textline_orientation": False,
            },
            {"lang": "en"},
            {
                "lang": "en",
                "use_angle_cls": False,
                "use_gpu": False,
                "show_log": False,
            },
        ]
        last_error = None
        for kwargs in attempts:
            try:
                paddle_ocr = PaddleOCR(**kwargs)
                break
            except TypeError as exc:
                last_error = exc
        if paddle_ocr is None:
            raise last_error or RuntimeError("Unable to initialize PaddleOCR")
    return paddle_ocr


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


def _box_bounds(box: Any) -> Dict[str, Optional[float]]:
    if box is None:
        return {"x0": None, "top": None, "x1": None, "bottom": None}
    arr = np.array(box, dtype=float)
    if arr.ndim == 1 and arr.size >= 4:
        x0, y0, x1, y1 = arr[:4]
        return {
            "x0": float(min(x0, x1)),
            "top": float(min(y0, y1)),
            "x1": float(max(x0, x1)),
            "bottom": float(max(y0, y1)),
        }
    if arr.ndim >= 2 and arr.shape[0] >= 2:
        xs = arr[:, 0]
        ys = arr[:, 1]
        return {
            "x0": float(xs.min()),
            "top": float(ys.min()),
            "x1": float(xs.max()),
            "bottom": float(ys.max()),
        }
    return {"x0": None, "top": None, "x1": None, "bottom": None}


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
                lines.append({
                    "text": text,
                    "x": x,
                    "y": y,
                    "h": h,
                    "score": score,
                    **_box_bounds(box),
                })
            continue

        page_lines = page if isinstance(page, list) else []
        for idx, line in enumerate(page_lines):
            text, box, score = _extract_text_from_v2_line(line)
            if not text:
                continue
            x, y, h = _box_center(box) if box is not None else (0.0, float(idx * 14), 12.0)
            lines.append({
                "text": text,
                "x": x,
                "y": y,
                "h": h,
                "score": score,
                **_box_bounds(box),
            })

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


def _merge_line_bounds(lines: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    bounded = [line for line in lines if line.get("x0") is not None]
    if not bounded:
        return {"x0": None, "top": None, "x1": None, "bottom": None}
    return {
        "x0": min(float(line["x0"]) for line in bounded),
        "top": min(float(line["top"]) for line in bounded),
        "x1": max(float(line["x1"]) for line in bounded),
        "bottom": max(float(line["bottom"]) for line in bounded),
    }


def ocr_lines_to_debug_page(
    lines: List[Dict[str, Any]],
    *,
    page_number: int,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> Dict[str, Any]:
    if not lines:
        return {
            "page_number": page_number,
            "width": width,
            "height": height,
            "word_count": 0,
            "words": [],
            "rows": [],
        }

    sorted_lines = sorted(lines, key=lambda item: (item["y"], item["x"]))
    median_height = float(np.median([line["h"] for line in sorted_lines]))
    y_tolerance = max(8.0, median_height * 0.65)

    grouped: List[List[Dict[str, Any]]] = []
    for line in sorted_lines:
        if not grouped or abs(grouped[-1][0]["y"] - line["y"]) > y_tolerance:
            grouped.append([line])
        else:
            grouped[-1].append(line)

    debug_rows: List[Dict[str, Any]] = []
    for row_index, group in enumerate(grouped):
        group = sorted(group, key=lambda item: item["x"])
        cells = []
        for cell_index, item in enumerate(group):
            cells.append({
                "cell_index": cell_index,
                "text": item["text"].strip(),
                "confidence": item.get("score"),
                "x0": item.get("x0"),
                "top": item.get("top"),
                "x1": item.get("x1"),
                "bottom": item.get("bottom"),
            })
        debug_rows.append({
            "row_index": row_index,
            "text": " | ".join(cell["text"] for cell in cells if cell["text"]),
            "cells": cells,
            **_merge_line_bounds(group),
        })

    debug_words = [
        {
            "word_index": idx,
            "text": line["text"],
            "confidence": line.get("score"),
            "x0": line.get("x0"),
            "top": line.get("top"),
            "x1": line.get("x1"),
            "bottom": line.get("bottom"),
        }
        for idx, line in enumerate(sorted_lines)
    ]

    return {
        "page_number": page_number,
        "width": width,
        "height": height,
        "word_count": len(debug_words),
        "words": debug_words,
        "rows": debug_rows,
    }


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

    return cells


def extract_ocr_rows(image: np.ndarray) -> List[List[str]]:
    try:
        ocr = _get_paddle_ocr()
        if hasattr(ocr, "predict"):
            result = ocr.predict(image)
        else:
            result = ocr.ocr(image, cls=False)
        lines = _normalize_ocr_lines(result)
        return ocr_lines_to_rows(lines)
    except Exception as e:
        LOGGER.error(f"Failed to extract OCR rows: {e}")
        return []


def extract_ocr_rows_with_debug(
    image: np.ndarray,
    *,
    page_number: int,
) -> Tuple[List[List[str]], Dict[str, Any]]:
    try:
        ocr = _get_paddle_ocr()
        if hasattr(ocr, "predict"):
            result = ocr.predict(image)
        else:
            result = ocr.ocr(image, cls=False)
        lines = _normalize_ocr_lines(result)
        rows = ocr_lines_to_rows(lines)
        height, width = image.shape[:2]
        debug_page = ocr_lines_to_debug_page(
            lines,
            page_number=page_number,
            width=int(width),
            height=int(height),
        )
        return rows, debug_page
    except Exception as e:
        LOGGER.error(f"Failed to extract OCR rows: {e}")
        return [], {
            "page_number": page_number,
            "width": None,
            "height": None,
            "word_count": 0,
            "words": [],
            "rows": [],
            "error": str(e),
        }
