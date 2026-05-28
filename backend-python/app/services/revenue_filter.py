"""
Revenue classification rules for extracted bank statement transactions.

The OCR/parser layer keeps the raw debit and credit amounts intact. This module
adds a second view over credits: accepted operational revenue vs filtered
non-revenue injections such as transfers, loans, corrections, and perks.
"""
import re
from typing import Dict, Iterable, List, Optional


OWNER_OR_BUSINESS_HINTS = [
    "sneads",
    "snead",
]


DEDUCTION_RULES = [
    (
        "Financing & Loans",
        [
            r"\badvances?\b",
            r"\b(?:loc|line\s+of\s+credit|olb|occ)\b",
            r"\bloan\b",
            r"\blender\b",
            r"\bequipment\s+finance\b",
            r"\bnextgear\b",
            r"\bcashflow\s+funding\b",
            r"\basset\s+lease\b",
            r"\bpersonal\s+loans?\b",
            r"\boverdraft\b",
            r"\bod\b",
            r"\bprovisional\s+credit\b",
            r"\btemporary\s+credit\b",
        ],
    ),
    (
        "Internal Transfers & Linked Accounts",
        [
            r"\ba2a\b",
            r"\baccount\s+to\s+account\b",
            r"\bcash\s*m(?:ana)?g?m?nt\b",
            r"\bcol\s+xfer\b",
            r"\bdeposit\s+transfer\b",
            r"\bfrom\s+(?:acct|account)\s*(?:x+|\*+)?\d{3,}\b",
            r"\b(?:acct|account)\s*(?:x+|\*+)?\d{3,}\b",
            r"\bpayroll\s+account\b",
            r"\bfunds?\s+transfers?\b",
            r"\btransfer(?:s|red)?\b",
            r"\bxfr\b",
            r"\bxfer\b",
            r"\bmobile\s+banking\s+transfer\b",
            r"\bonline\s+banking\s+transfer\b",
            r"\bonline\s+xfer\b",
            r"\bonline\s+transfer\b",
            r"\bfrom\s+(?:chk|checking|savings|mma|payroll)\b",
            r"\bpc\s+transfer\b",
            r"\btelephone\s+transfer\b",
            r"\btele\s+transfer\b",
            r"\bacorns\b",
            r"\bmoney\s+transfer\b",
        ],
    ),
    (
        "Banking Corrections, Reversals & Perks",
        [
            r"\bcredit\s+adjust(?:ment)?\b",
            r"\bwithdrawal\s+adjustment\b",
            r"\bdebit\s+card\s+credit\s+voucher\b",
            r"\bdeposit\s+correction\b",
            r"\bshare\s+draft\s+correction\b",
            r"\berror\s+deposit\b",
            r"\bmisposted\b",
            r"\bnsf\b",
            r"\breturns?\b",
            r"\brtn\b",
            r"\bret\b",
            r"\bcash\s*back\b",
            r"\brewards?\b",
            r"\brebates?\b",
            r"\brbt\b",
            r"\bdividends?\b",
            r"\binterest\b",
            r"\brefunds?\b",
            r"\btreas(?:ury)?\b",
            r"\bvouchers?\b",
            r"\bfees?\b",
            r"\bfee\s+reversal\b",
            r"\btrial\s+deposit\b",
            r"\bverify\s+deposit\b",
        ],
    ),
]


WIRE_DEDUCTION_PATTERNS = [
    r"\bmerchant\b",
    r"\bloc\b",
    r"\bline\s+of\s+credit\b",
    r"\blender\b",
    r"\bloan\b",
    r"\bfunding\b",
    r"\bfinance\b",
]


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _first_rule_match(text: str, rules: Iterable[tuple]) -> Optional[Dict[str, str]]:
    for category, patterns in rules:
        for pattern in patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return {
                    "status": "deduction",
                    "reason": category,
                    "rule": pattern,
                }
    return None


def classify_credit_revenue(
    description: str,
    *,
    account_holder: Optional[str] = None,
    business_name: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """
    Return revenue status metadata for a credit transaction.

    Standard business wires are accepted unless the sender text also looks like
    a merchant, lender, or LOC injection.
    """
    text = _normalise(description)
    if not text:
        return {
            "status": "revenue",
            "reason": None,
            "rule": None,
        }

    owner_hints = [account_holder, business_name, *OWNER_OR_BUSINESS_HINTS]
    for hint in owner_hints:
        hint_norm = _normalise(hint or "")
        if hint_norm and hint_norm in text and re.search(r"\bmoney\s+transfer\b|\bauth(?:orized)?\b", text):
            return {
                "status": "deduction",
                "reason": "Internal Transfers & Linked Accounts",
                "rule": "owner/business authorized money transfer",
            }

    if re.search(r"\bwire\b", text):
        for pattern in WIRE_DEDUCTION_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return {
                    "status": "deduction",
                    "reason": "Special Conditional Rule: Wire Deposits",
                    "rule": pattern,
                }
        return {
            "status": "revenue",
            "reason": None,
            "rule": "standard business wire kept as revenue",
        }

    matched = _first_rule_match(text, DEDUCTION_RULES)
    if matched:
        return matched

    return {
        "status": "revenue",
        "reason": None,
        "rule": None,
    }


def apply_revenue_filter(transactions: List) -> Dict[str, float]:
    raw_credits = 0.0
    adjusted_revenue = 0.0
    revenue_deductions = 0.0
    total_debits = 0.0

    for transaction in transactions:
        credit = float(transaction.credit or 0)
        debit = float(transaction.debit or 0)
        total_debits += debit

        if credit <= 0:
            transaction.transaction_type = "debit" if debit > 0 else "unknown"
            transaction.revenue_status = None
            transaction.revenue_deduction_reason = None
            transaction.revenue_rule = None
            transaction.adjusted_revenue_amount = None
            continue

        raw_credits += credit
        classification = classify_credit_revenue(transaction.description)
        transaction.transaction_type = "credit"
        transaction.revenue_status = classification["status"]
        transaction.revenue_deduction_reason = classification["reason"]
        transaction.revenue_rule = classification["rule"]

        if classification["status"] == "deduction":
            revenue_deductions += credit
            transaction.adjusted_revenue_amount = 0.0
        else:
            adjusted_revenue += credit
            transaction.adjusted_revenue_amount = credit

    return {
        "raw_credits": round(raw_credits, 2),
        "adjusted_revenue": round(adjusted_revenue, 2),
        "revenue_deductions": round(revenue_deductions, 2),
        "total_debits": round(total_debits, 2),
    }
