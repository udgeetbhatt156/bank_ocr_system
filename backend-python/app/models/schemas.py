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


class OCRResponse(BaseModel):
    """Complete OCR processing response"""
    status: str
    documents: List[StatementResult]
