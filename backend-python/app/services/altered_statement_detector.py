"""
Altered statement detection.

This is an early risk screen, not a legal/fraud determination. It blocks only
high-risk documents that show multiple strong manipulation indicators.
"""
from dataclasses import dataclass, field
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

import fitz

LOGGER = logging.getLogger(__name__)


HIGH_RISK_THRESHOLD = 70
MEDIUM_RISK_THRESHOLD = 45

PDF_EDITOR_PATTERNS = [
    "adobe illustrator",
    "adobe photoshop",
    "canva",
    "figma",
    "ilovepdf",
    "sejda",
    "smallpdf",
    "pdfescape",
    "foxit phantompdf",
    "wondershare",
]

SUSPICIOUS_TEXT_PATTERNS = [
    r"\bvoid\b",
    r"\bsample\b",
    r"\bdraft\b",
    r"\btemplate\b",
    r"\baltered\b",
    r"\bedited\b",
    r"\bfor\s+illustration\b",
    r"\bnot\s+an?\s+(?:official|formal)\s+statement\b",
]

BANKING_KEYWORDS = [
    "statement",
    "account",
    "balance",
    "deposit",
    "withdrawal",
    "transaction",
    "debit",
    "credit",
]


@dataclass
class AlterationCheckResult:
    is_altered: bool
    risk_score: int
    risk_level: str
    reasons: List[str] = field(default_factory=list)
    signals: Dict[str, object] = field(default_factory=dict)

    @property
    def message(self) -> str:
        if not self.is_altered:
            return "No high-risk alteration indicators detected."
        return "Statement rejected because high-risk alteration indicators were detected."


def _risk_level(score: int) -> str:
    if score >= HIGH_RISK_THRESHOLD:
        return "high"
    if score >= MEDIUM_RISK_THRESHOLD:
        return "medium"
    return "low"


def _metadata_text(doc: fitz.Document) -> str:
    metadata = doc.metadata or {}
    return " ".join(str(value or "") for value in metadata.values()).lower()


def _page_text_sample(doc: fitz.Document, max_pages: int = 4) -> str:
    chunks: List[str] = []
    for page_index in range(min(max_pages, len(doc))):
        page = doc[page_index]
        chunks.append(page.get_text("text") or "")
    return "\n".join(chunks)


def _count_incremental_updates(file_path: Path) -> int:
    try:
        raw = file_path.read_bytes()
    except Exception:
        return 0
    # Multiple EOF markers are common after PDF editing/saving-in-place.
    return max(0, raw.count(b"%%EOF") - 1)


def _has_mixed_text_and_full_page_image(page: fitz.Page) -> bool:
    text_len = len((page.get_text("text") or "").strip())
    if text_len < 40:
        return False

    page_area = max(float(page.rect.width * page.rect.height), 1.0)
    for image in page.get_images(full=True):
        xref = image[0]
        for rect in page.get_image_rects(xref):
            if (rect.width * rect.height) / page_area > 0.65:
                return True
    return False


def _font_fragmentation_score(page: fitz.Page) -> int:
    try:
        fonts = page.get_fonts(full=True)
    except Exception:
        return 0
    font_names = {str(font[3]).lower() for font in fonts if len(font) > 3}
    # Most genuine generated statements use a small font set. Lots of embedded
    # subset fonts can indicate layered edits or OCR-over-PDF reconstruction.
    return max(0, len(font_names) - 8)


def detect_altered_statement(file_path: Path) -> AlterationCheckResult:
    """
    Return an alteration risk result for a PDF/image before OCR parsing.

    The detector intentionally requires multiple signals before rejection to
    avoid blocking ordinary scanned or bank-generated PDFs.
    """
    suffix = file_path.suffix.lower()
    if suffix not in {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif"}:
        return AlterationCheckResult(
            is_altered=True,
            risk_score=100,
            risk_level="high",
            reasons=["Unsupported file type for bank statement processing."],
            signals={"suffix": suffix},
        )

    if suffix != ".pdf":
        return AlterationCheckResult(
            is_altered=False,
            risk_score=0,
            risk_level="low",
            reasons=[],
            signals={"file_type": "image"},
        )

    score = 0
    reasons: List[str] = []
    signals: Dict[str, object] = {}

    try:
        incremental_updates = _count_incremental_updates(file_path)
        signals["incremental_updates"] = incremental_updates
        if incremental_updates >= 2:
            score += 25
            reasons.append("PDF contains multiple incremental save/update markers.")

        with fitz.open(file_path) as doc:
            if doc.is_encrypted:
                score += 30
                reasons.append("PDF is encrypted or permission-restricted.")

            metadata_text = _metadata_text(doc)
            matched_editors = [
                pattern for pattern in PDF_EDITOR_PATTERNS if pattern in metadata_text
            ]
            signals["matched_pdf_editors"] = matched_editors
            if matched_editors:
                score += 35
                reasons.append(
                    "PDF metadata indicates editing software: "
                    + ", ".join(matched_editors[:3])
                )

            text_sample = _page_text_sample(doc)
            lowered_text = text_sample.lower()
            suspicious_terms = [
                pattern
                for pattern in SUSPICIOUS_TEXT_PATTERNS
                if re.search(pattern, lowered_text)
            ]
            signals["suspicious_text_patterns"] = suspicious_terms
            if suspicious_terms:
                score += 35
                reasons.append("Document text contains suspicious draft/template markers.")

            banking_keyword_count = sum(1 for keyword in BANKING_KEYWORDS if keyword in lowered_text)
            signals["banking_keyword_count"] = banking_keyword_count
            if len(text_sample.strip()) > 300 and banking_keyword_count < 2:
                score += 20
                reasons.append("Text layer does not resemble a bank statement.")

            mixed_overlay_pages = 0
            fragmented_pages = 0
            redaction_annotations = 0
            for page_index in range(min(5, len(doc))):
                page = doc[page_index]
                if _has_mixed_text_and_full_page_image(page):
                    mixed_overlay_pages += 1
                if _font_fragmentation_score(page) >= 4:
                    fragmented_pages += 1
                for annot in page.annots() or []:
                    annot_type = annot.type[1] if annot.type else ""
                    if str(annot_type).lower() in {"redact", "freetext", "stamp"}:
                        redaction_annotations += 1

            signals["mixed_overlay_pages"] = mixed_overlay_pages
            signals["fragmented_font_pages"] = fragmented_pages
            signals["redaction_or_free_text_annotations"] = redaction_annotations

            if mixed_overlay_pages >= 2:
                score += 25
                reasons.append("PDF has image-backed pages with an additional text layer.")
            if fragmented_pages >= 2:
                score += 20
                reasons.append("PDF uses unusually fragmented embedded fonts.")
            if redaction_annotations > 0:
                score += 40
                reasons.append("PDF contains redaction, free-text, or stamp annotations.")

    except Exception as exc:
        LOGGER.warning("Alteration screening failed for %s: %s", file_path.name, exc)
        return AlterationCheckResult(
            is_altered=False,
            risk_score=0,
            risk_level="low",
            reasons=[f"Alteration screening could not be completed: {exc}"],
            signals={"screening_error": str(exc)},
        )

    score = min(score, 100)
    risk_level = _risk_level(score)
    return AlterationCheckResult(
        is_altered=score >= HIGH_RISK_THRESHOLD,
        risk_score=score,
        risk_level=risk_level,
        reasons=reasons,
        signals=signals,
    )
