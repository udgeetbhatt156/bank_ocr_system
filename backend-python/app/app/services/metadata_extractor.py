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
    (r"\bjpmorgan\b", "JPMorgan Chase"),
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
    (r"\bfifth\s+third\b", "Fifth Third Bank"),
    (r"\bkey\s*bank\b", "KeyBank"),
    (r"\bsantander\b", "Santander Bank"),
    (r"\bm&t\b", "M&T Bank"),
    (r"\bhuntington\b", "Huntington Bank"),
    (r"\bcitizens\b", "Citizens Bank"),
    (r"\bdiscover\b", "Discover Bank"),
    (r"\bbbva\b", "BBVA"),
    (r"\bsuntrust\b", "SunTrust"),
    (r"\bfirst\s+national\b", "First National Bank"),
    (r"\bfirst\s+enterprise\b", "First Enterprise Bank"),
    (r"\bfirst\s+kansas\b", "First Kansas Bank"),
    (r"\bfirst\s+service\b", "First Service Bank"),
    (r"\bfive\s+star\b", "Five Star Bank"),
    (r"\bforbright\b", "Forbright Bank"),
    (r"\bindiana\s+members\b", "Indiana Members Credit Union"),
    (r"\blmcu\b", "Lake Michigan Credit Union"),
    (r"\bmercury\b", "Mercury Bank"),
    (r"\bstellar\b", "Stellar Bank"),
    (r"\bexchange\s+bank\b", "Exchange Bank"),
    (r"\bwayne\s+bank\b", "Wayne Bank"),
    (r"\btimberlake\b", "Timberlake Bank"),
    (r"\bpeoplessouth\b", "PeopleSouth Bank"),
    (r"\bbancfirst\b", "BancFirst"),
    (r"\bbancorpsouth\b", "BancorpSouth"),
    # Additional Major US Banks
    (r"\bamerican\s+express\b", "American Express Bank"),
    (r"\bamex\b", "American Express Bank"),
    (r"\bsofi\b", "SoFi Bank"),
    (r"\bwoodforest\b", "Woodforest National Bank"),
    (r"\bsynchrony\b", "Synchrony Bank"),
    (r"\bcomerica\b", "Comerica Bank"),
    (r"\bfirstbank\b", "FirstBank"),
    (r"\bzions\b", "Zions Bank"),
    (r"\beast\s+west\b", "East West Bank"),
    (r"\bunion\s+bank\b", "Union Bank"),
    (r"\bfrost\b", "Frost Bank"),
    (r"\bwebster\b", "Webster Bank"),
    (r"\bubs\b", "UBS Bank"),
    (r"\bcharles\s+schwab\b", "Charles Schwab Bank"),
    (r"\bfidelity\b", "Fidelity Investments"),
    (r"\bhsbc\b", "HSBC Bank"),
    (r"\bbarclays\b", "Barclays Bank"),
    (r"\bbrex\b", "Brex"),
    (r"\bwise\b", "Wise"),
    (r"\brevolut\b", "Revolut"),
    (r"\bvaro\b", "Varo Bank"),
    (r"\bcurrent\b", "Current"),
    (r"\bgreen\s*dot\b", "Green Dot Bank"),
    (r"\bchime\b", "Chime"),
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
