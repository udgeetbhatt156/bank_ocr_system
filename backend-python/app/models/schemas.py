"""
Pydantic models for API request/response
"""
from typing import List, Optional
from pydantic import BaseModel


class Transaction(BaseModel):
    """Single transaction record"""
    date: Optional[str] = None
    description: str
    debit: Optional[float] = None
    credit: Optional[float] = None
    balance: Optional[float] = None
    reference: Optional[str] = None
    source_line: str
    transaction_type: Optional[str] = None
    revenue_status: Optional[str] = None
    revenue_deduction_reason: Optional[str] = None
    revenue_rule: Optional[str] = None
    adjusted_revenue_amount: Optional[float] = None


class StatementResult(BaseModel):
    """Result from processing a single statement"""
    filename: str
    transactions: List[Transaction]
    confidence: float
    pdf_type: str  # "digital" or "scanned"
    warnings: List[str] = []
    raw_text: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    customer_number: Optional[str] = None
    current_balance: Optional[float] = None
    raw_credits: float = 0.0
    adjusted_revenue: float = 0.0
    revenue_deductions: float = 0.0
    total_debits: float = 0.0
    # Duplicate detection fields
    file_hash: Optional[str] = None
    content_hash: Optional[str] = None
    is_duplicate: bool = False
    duplicate_type: Optional[str] = None
    duplicate_of: Optional[str] = None
    duplicate_confidence: Optional[float] = None
    duplicate_message: Optional[str] = None


class OCRResponse(BaseModel):
    """Complete OCR processing response"""
    status: str
    documents: List[StatementResult]
