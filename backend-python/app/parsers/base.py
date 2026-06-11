"""Base parser contract for bank statement parsers."""

from abc import ABC, abstractmethod
from typing import List

from app.models.schemas import Transaction
from app.parsers.context import ParserContext
from app.parsers.result import ParseResult, StatementMetadata


class BaseParser(ABC):
    """Interface implemented by all bank/layout-specific parsers."""

    parser_id = "base"

    def __init__(self, context: ParserContext) -> None:
        self.context = context

    @abstractmethod
    def extract_metadata(self) -> StatementMetadata:
        """Extract statement-level metadata from the parser context."""

    @abstractmethod
    def extract_transactions(self) -> List[Transaction]:
        """Extract normalized transaction records from the parser context."""

    @abstractmethod
    def parse(self) -> ParseResult:
        """Run metadata and transaction extraction and return normalized output."""
