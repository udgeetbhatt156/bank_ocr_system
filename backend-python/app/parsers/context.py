"""Shared parser input context."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ParserContext:
    """Normalized input passed to every parser implementation."""

    rows: List[List[str]]
    raw_text: str = ""
    pdf_type: str = "unknown"
    filename: str = ""
    bank_id: Optional[str] = None
    bank_hint: Optional[str] = None
    template_id: Optional[str] = None
    parser_format: Optional[str] = None
    statement_year: Optional[int] = None
    statement_month: Optional[int] = None
    debug_extraction: Dict[str, Any] = field(default_factory=dict)
