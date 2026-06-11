"""Parser registry for bank and template parser lookup."""

from typing import Dict, Optional, Type

from app.parsers.base import BaseParser

ParserClass = Type[BaseParser]

PARSER_REGISTRY: Dict[str, ParserClass] = {}
TEMPLATE_PARSER_REGISTRY: Dict[str, ParserClass] = {}
FORMAT_PARSER_REGISTRY: Dict[str, ParserClass] = {}


def normalize_registry_key(value: Optional[str]) -> Optional[str]:
    """Normalize bank identifiers for registry lookup."""
    if not value:
        return None
    return value.strip().replace("-", "_").replace(" ", "_").upper()


def register_parser(bank_id: str, parser_cls: ParserClass) -> None:
    """Register a parser class for a normalized bank identifier."""
    normalized = normalize_registry_key(bank_id)
    if not normalized:
        raise ValueError("bank_id is required")
    PARSER_REGISTRY[normalized] = parser_cls


def register_template_parser(template_id: str, parser_cls: ParserClass) -> None:
    """Register a parser class for a statement template id."""
    if not template_id:
        raise ValueError("template_id is required")
    TEMPLATE_PARSER_REGISTRY[template_id] = parser_cls


def register_format_parser(parser_format: str, parser_cls: ParserClass) -> None:
    """Register a parser class for a reusable parser format/layout."""
    if not parser_format:
        raise ValueError("parser_format is required")
    FORMAT_PARSER_REGISTRY[parser_format] = parser_cls


def get_parser_class(bank_id: Optional[str]) -> Optional[ParserClass]:
    """Return a parser class for a bank id if one is registered."""
    normalized = normalize_registry_key(bank_id)
    if not normalized:
        return None
    return PARSER_REGISTRY.get(normalized)


def get_template_parser_class(template_id: Optional[str]) -> Optional[ParserClass]:
    """Return a parser class for a template id if one is registered."""
    if not template_id:
        return None
    return TEMPLATE_PARSER_REGISTRY.get(template_id)


def get_format_parser_class(parser_format: Optional[str]) -> Optional[ParserClass]:
    """Return a parser class for a parser format if one is registered."""
    if not parser_format:
        return None
    return FORMAT_PARSER_REGISTRY.get(parser_format)
