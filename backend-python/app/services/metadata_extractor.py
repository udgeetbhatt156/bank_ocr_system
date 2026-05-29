"""
Extract statement-level metadata from OCR rows and parsed transactions.
Tuned for US bank statements (BMO, Suncoast, U.S. Bank, Chase, etc.).
"""
import re
from typing import Any, Dict, List, Optional

from app.models.schemas import Transaction

US_BANK_PATTERNS = [
    # Major National Banks (Priority Order)
    (r"\bbank\s+of\s+america\b", "Bank of America"),
    (r"\bwells\s*fargo\b", "Wells Fargo"),
    (r"\bjpmorgan\s+chase\b", "JPMorgan Chase"),
    (r"\bchase\s+bank\b", "Chase"),
    (r"\bchase\b", "Chase"),
    (r"\bciti(?:bank|group)?\b", "Citibank"),
    (r"\bus\s*bank\b", "U.S. Bank"),
    (r"\bpnc\s+bank\b", "PNC Bank"),
    (r"\bpnc\b", "PNC Bank"),
    (r"\bcapital\s+one\b", "Capital One"),
    (r"\btd\s+bank\b", "TD Bank"),
    (r"\btruist\b", "Truist"),
    (r"\bfifth\s+third\b", "Fifth Third Bank"),
    (r"\bregions\s+bank\b", "Regions Bank"),
    (r"\bregions\b", "Regions Bank"),
    (r"\bm&t\s+bank\b", "M&T Bank"),
    (r"\bm&t\b", "M&T Bank"),
    (r"\bhuntington\s+bank\b", "Huntington Bank"),
    (r"\bhuntington\b", "Huntington Bank"),
    (r"\bkey\s*bank\b", "KeyBank"),
    (r"\bcitizens\s+bank\b", "Citizens Bank"),
    (r"\bcitizens\b", "Citizens Bank"),
    (r"\bsantander\b", "Santander Bank"),
    (r"\bbbva\b", "BBVA"),
    (r"\bcomerica\b", "Comerica Bank"),
    (r"\bzions\s+bank\b", "Zions Bank"),
    (r"\bzions\b", "Zions Bank"),
    
    # Regional & Community Banks
    (r"\bbmo\s+(?:harris\s+)?bank\b", "BMO Bank"),
    (r"\bbmo\b", "BMO Bank"),
    (r"\bsuncoast\s+credit\s+union\b", "Suncoast Credit Union"),
    (r"\bsuncoast\b", "Suncoast Credit Union"),
    (r"\bpeoplessouth\s+bank\b", "PeopleSouth Bank"),
    (r"\bpeoplessouth\b", "PeopleSouth Bank"),
    (r"\bbancfirst\b", "BancFirst"),
    (r"\bbancorpsouth\b", "BancorpSouth"),
    (r"\bfirst\s+national\s+bank\b", "First National Bank"),
    (r"\bfirst\s+enterprise\s+bank\b", "First Enterprise Bank"),
    (r"\bfirst\s+kansas\s+bank\b", "First Kansas Bank"),
    (r"\bfirst\s+service\s+bank\b", "First Service Bank"),
    (r"\bfirstbank\b", "FirstBank"),
    (r"\bfive\s+star\s+bank\b", "Five Star Bank"),
    (r"\bforbright\s+bank\b", "Forbright Bank"),
    (r"\bstellar\s+bank\b", "Stellar Bank"),
    (r"\bexchange\s+bank\b", "Exchange Bank"),
    (r"\bwayne\s+bank\b", "Wayne Bank"),
    (r"\btimberlake\s+bank\b", "Timberlake Bank"),
    (r"\bfrost\s+bank\b", "Frost Bank"),
    (r"\bfrost\b", "Frost Bank"),
    (r"\bwebster\s+bank\b", "Webster Bank"),
    (r"\bwebster\b", "Webster Bank"),
    (r"\beast\s+west\s+bank\b", "East West Bank"),
    (r"\bunion\s+bank\b", "Union Bank"),
    (r"\bwoodforest\s+national\s+bank\b", "Woodforest National Bank"),
    (r"\bwoodforest\b", "Woodforest National Bank"),
    
    # Credit Unions
    (r"\bnavy\s+federal\s+credit\s+union\b", "Navy Federal Credit Union"),
    (r"\bnavy\s+federal\b", "Navy Federal Credit Union"),
    (r"\bindiana\s+members\s+credit\s+union\b", "Indiana Members Credit Union"),
    (r"\bindiana\s+members\b", "Indiana Members Credit Union"),
    (r"\blake\s+michigan\s+credit\s+union\b", "Lake Michigan Credit Union"),
    (r"\blmcu\b", "Lake Michigan Credit Union"),
    
    # Online & Fintech Banks
    (r"\bally\s+bank\b", "Ally Bank"),
    (r"\bally\b", "Ally Bank"),
    (r"\bdiscover\s+bank\b", "Discover Bank"),
    (r"\bdiscover\b", "Discover Bank"),
    (r"\bsofi\s+bank\b", "SoFi Bank"),
    (r"\bsofi\b", "SoFi Bank"),
    (r"\bsynchrony\s+bank\b", "Synchrony Bank"),
    (r"\bsynchrony\b", "Synchrony Bank"),
    (r"\bmercury\b", "Mercury Bank"),
    (r"\bbrex\b", "Brex"),
    (r"\bwise\b", "Wise"),
    (r"\brevolut\b", "Revolut"),
    (r"\bvaro\s+bank\b", "Varo Bank"),
    (r"\bvaro\b", "Varo Bank"),
    (r"\bcurrent\b", "Current"),
    (r"\bgreen\s*dot\s+bank\b", "Green Dot Bank"),
    (r"\bgreen\s*dot\b", "Green Dot Bank"),
    (r"\bchime\b", "Chime"),
    
    # Investment & Brokerage Banks
    (r"\bamerican\s+express\s+bank\b", "American Express Bank"),
    (r"\bamex\b", "American Express Bank"),
    (r"\bcharles\s+schwab\s+bank\b", "Charles Schwab Bank"),
    (r"\bcharles\s+schwab\b", "Charles Schwab Bank"),
    (r"\bfidelity\s+investments\b", "Fidelity Investments"),
    (r"\bfidelity\b", "Fidelity Investments"),
    (r"\bubs\s+bank\b", "UBS Bank"),
    (r"\bubs\b", "UBS Bank"),
    
    # International Banks (US Operations)
    (r"\bhsbc\s+bank\b", "HSBC Bank"),
    (r"\bhsbc\b", "HSBC Bank"),
    (r"\bbarclays\s+bank\b", "Barclays Bank"),
    (r"\bbarclays\b", "Barclays Bank"),
    (r"\bsuntrust\b", "SunTrust"),
]


def _flatten_text(rows: List[List[str]], max_rows: int = 50) -> str:
    parts = []
    for row in rows[:max_rows]:
        parts.append(" ".join(str(c) for c in row))
    return "\n".join(parts)


def _detect_bank_name(text: str) -> Optional[str]:
    """
    Detect bank name from statement text using comprehensive pattern matching.
    
    Strategy:
    1. Try exact pattern matches first (most reliable)
    2. Look for capitalized bank names with keywords
    3. Return None if no confident match
    """
    text_lower = text.lower()
    
    # Try all known bank patterns (ordered by specificity)
    for pattern, name in US_BANK_PATTERNS:
        if re.search(pattern, text_lower):
            return name

    # Fallback: Look for capitalized bank names
    # Pattern: "Capital Word(s) Bank/Credit Union/CU"
    m = re.search(
        r"\b([A-Z][A-Za-z0-9\s&.'-]{2,40}(?:Bank|Credit Union|CU|Financial))\b",
        text,
    )
    if m:
        candidate = m.group(1).strip()
        # Filter out common false positives
        if len(candidate) > 4 and not candidate.lower().startswith("the "):
            # Additional validation: check if it looks like a real bank name
            if not re.search(r"\b(statement|account|balance|transaction|date)\b", candidate, re.IGNORECASE):
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
