"""Parser architecture scaffold for bank statement extraction."""

import app.parsers.banks  # Registers bank parser classes.

from app.parsers.base import BaseParser
from app.parsers.builder import ParserBuilder, ParserNotFoundError
from app.parsers.context import ParserContext
from app.parsers.result import ParseResult, StatementMetadata

__all__ = [
    "BaseParser",
    "ParseResult",
    "ParserBuilder",
    "ParserContext",
    "ParserNotFoundError",
    "StatementMetadata",
]
