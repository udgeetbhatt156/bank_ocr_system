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

        try:
            paddle_ocr = PaddleOCR(
                lang="en",
                use_angle_cls=False,
                use_gpu=False,
                show_log=False,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        except TypeError:
            paddle_ocr = PaddleOCR(
                lang="en",
                use_angle_cls=False,
                use_gpu=False,
                show_log=False,
            )
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

    return cells


def extract_ocr_rows(image: np.ndarray) -> List[List[str]]:
    try:
        ocr = _get_paddle_ocr()
        result = ocr.ocr(image, cls=False)
        lines = _normalize_ocr_lines(result)
        return ocr_lines_to_rows(lines)
    except Exception as e:
        LOGGER.error(f"Failed to extract OCR rows: {e}")
        return []
