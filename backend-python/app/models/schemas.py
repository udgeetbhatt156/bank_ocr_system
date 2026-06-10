"""
Pydantic models for API request/response
"""
from typing import List, Optional
from typing import Any, Dict
from pydantic import BaseModel, Field


class Transaction(BaseModel):
    """Single transaction record"""
    date: Optional[str] = None
    description: str
    debit: Optional[float] = None
    credit: Optional[float] = None
    balance: Optional[float] = None


class StatementResult(BaseModel):
    """Result from processing a single statement"""
    filename: str
    transactions: List[Transaction]
    confidence: float
    pdf_type: str  # "digital" or "scanned"
    warnings: List[str] = []
    raw_text: Optional[str] = None
    debug_extraction: Dict[str, Any] = Field(default_factory=dict)
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    customer_name: Optional[str] = None
    current_balance: Optional[float] = None
    total_debits: float = 0.0
    total_credits: float = 0.0
    # Duplicate detection fields
    file_hash: Optional[str] = None
    content_hash: Optional[str] = None
    is_duplicate: bool = False
    duplicate_type: Optional[str] = None
    duplicate_of: Optional[str] = None
    duplicate_confidence: Optional[float] = None
    duplicate_message: Optional[str] = None
    # Altered/fraud-risk detection fields
    is_altered: bool = False
    alteration_risk_score: int = 0
    alteration_risk_level: Optional[str] = None
    alteration_reasons: List[str] = Field(default_factory=list)
    alteration_signals: Dict[str, Any] = Field(default_factory=dict)
    rejected: bool = False
    rejection_reason: Optional[str] = None


class OCRResponse(BaseModel):
    """Complete OCR processing response"""
    status: str
    documents: List[StatementResult]
