"""Factory for resolving parser classes from bank/template context."""

from typing import Optional

from app.parsers.base import BaseParser
from app.parsers.context import ParserContext
from app.parsers.registry import (
    get_format_parser_class,
    get_parser_class,
    get_template_parser_class,
)


class ParserNotFoundError(ValueError):
    """Raised when no parser is registered for the requested context."""


class ParserBuilder:
    """Build parser instances using template, bank, then format fallback."""

    @staticmethod
    def get_parser(
        bank_id: Optional[str],
        context: ParserContext,
        *,
        template_id: Optional[str] = None,
        parser_format: Optional[str] = None,
    ) -> BaseParser:
        parser_cls = (
            get_template_parser_class(template_id or context.template_id)
            or get_parser_class(bank_id or context.bank_id)
            or get_format_parser_class(parser_format or context.parser_format)
        )
        if parser_cls is None:
            lookup_value = template_id or context.template_id or bank_id or context.bank_id
            raise ParserNotFoundError(f"No parser registered for {lookup_value!r}")
        return parser_cls(context)
