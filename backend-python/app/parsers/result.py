"""Normalized parser output models."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.models.schemas import Transaction


@dataclass
class StatementMetadata:
    """Statement-level metadata normalized across bank parsers."""

    bank_id: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    account_holder: Optional[str] = None
    customer_name: Optional[str] = None
    customer_address: Optional[str] = None
    account_type: Optional[str] = None
    statement_date: Optional[str] = None
    statement_start_date: Optional[str] = None
    statement_end_date: Optional[str] = None
    opening_balance: Optional[float] = None
    closing_balance: Optional[float] = None
    current_balance: Optional[float] = None
    total_credits: Optional[float] = None
    credit_count: Optional[int] = None
    total_debits: Optional[float] = None
    debit_count: Optional[int] = None
    service_charge: Optional[float] = None
    overdraft_fees_this_period: Optional[float] = None
    overdraft_fees_ytd: Optional[float] = None
    returned_item_fees_this_period: Optional[float] = None
    returned_item_fees_ytd: Optional[float] = None


@dataclass
class ParseResult:
    """Parser result before conversion to the public StatementResult schema."""

    metadata: StatementMetadata = field(default_factory=StatementMetadata)
    transactions: List[Transaction] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    confidence: float = 0.0
    parser_id: Optional[str] = None
    bank_id: Optional[str] = None
    template_id: Optional[str] = None
    checks_register: List[Dict[str, Any]] = field(default_factory=list)
    validation_errors: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)
