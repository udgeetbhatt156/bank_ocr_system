"""
Extract statement-level metadata from OCR rows and parsed transactions.
Tuned for US bank statements (BMO, Suncoast, U.S. Bank, Chase, etc.).
"""
import re
from typing import Any, Dict, List, Optional

from app.models.schemas import Transaction

US_BANK_PATTERNS = [
    (r"\bbmo\b", "BMO Bank"),
    (r"\bsuncoast\b", "Suncoast Credit Union"),
    (r"\bus\s*bank\b", "U.S. Bank"),
    (r"\bchase\b", "Chase"),
    (r"\bwells\s*fargo\b", "Wells Fargo"),
    (r"\bbank\s+of\s+america\b", "Bank of America"),
    (r"\bciti(?:bank)?\b", "Citibank"),
    (r"\bcapital\s+one\b", "Capital One"),
    (r"\bpnc\b", "PNC Bank"),
    (r"\btd\s+bank\b", "TD Bank"),
    (r"\btruist\b", "Truist"),
    (r"\bally\b", "Ally Bank"),
    (r"\bregions\b", "Regions Bank"),
    (r"\bnavy\s+federal\b", "Navy Federal Credit Union"),
]


def _flatten_text(rows: List[List[str]], max_rows: int = 50) -> str:
    parts = []
    for row in rows[:max_rows]:
        parts.append(" ".join(str(c) for c in row))
    return "\n".join(parts)


def _detect_bank_name(text: str) -> Optional[str]:
    text_lower = text.lower()
    for pattern, name in US_BANK_PATTERNS:
        if re.search(pattern, text_lower):
            return name

    m = re.search(
        r"([A-Z][A-Za-z0-9\s&.'-]{2,40}(?:Bank|Credit Union|CU))\b",
        text,
    )
    if m:
        candidate = m.group(1).strip()
        if len(candidate) > 4 and not candidate.lower().startswith("the "):
            return candidate
    return None


def _extract_account_number(text: str) -> Optional[str]:
    patterns = [
        r"account\s*(?:number|no\.?|#)\s*[:\s]*([*\dXx\-]{4,24})",
        r"checking\s*(?:account|acct)\s*(?:number|no\.?)?\s*[:\s#]*([*\dXx\-]{4,24})",
        r"savings\s*(?:account|acct)\s*(?:number|no\.?)?\s*[:\s#]*([*\dXx\-]{4,24})",
        r"acct\.?\s*(?:number|no\.?)?\s*[:\s#]*([*\dXx\-]{8,24})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _extract_customer_number(text: str) -> Optional[str]:
    patterns = [
        r"customer\s*(?:number|no\.?|id)\s*[:\s]*([A-Za-z0-9\-]{4,24})",
        r"member\s*(?:number|no\.?|id)\s*[:\s]*([A-Za-z0-9\-]{4,24})",
        r"client\s*(?:number|no\.?|id)\s*[:\s]*([A-Za-z0-9\-]{4,24})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _parse_balance_amount(raw: str) -> Optional[float]:
    cleaned = raw.replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_current_balance(
    text: str, transactions: List[Transaction]
) -> Optional[float]:
    patterns = [
        r"ending\s+balance\s*[:\s]*\$?\s*([\d,]+\.\d{2})",
        r"closing\s+balance\s*[:\s]*\$?\s*([\d,]+\.\d{2})",
        r"current\s+balance\s*[:\s]*\$?\s*([\d,]+\.\d{2})",
        r"new\s+balance\s*[:\s]*\$?\s*([\d,]+\.\d{2})",
        r"balance\s+forward\s*[:\s]*\$?\s*([\d,]+\.\d{2})",
        r"available\s+balance\s*[:\s]*\$?\s*([\d,]+\.\d{2})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            bal = _parse_balance_amount(m.group(1))
            if bal is not None:
                return bal

    for t in reversed(transactions):
        if t.balance is not None:
            return float(t.balance)
    return None


def extract_statement_metadata(
    rows: List[List[str]],
    transactions: List[Transaction],
    header_idx: Optional[int] = None,
) -> Dict[str, Any]:
    del header_idx  # reserved for future header-scoped parsing
    text = _flatten_text(rows)
    return {
        "bank_name": _detect_bank_name(text),
        "account_number": _extract_account_number(text),
        "customer_number": _extract_customer_number(text),
        "current_balance": _extract_current_balance(text, transactions),
    }
