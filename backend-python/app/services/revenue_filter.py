"""
Revenue classification rules for extracted bank statement transactions.

The OCR/parser layer keeps the raw debit and credit amounts intact. This module
adds a second view over credits: accepted operational revenue vs filtered
non-revenue injections such as transfers, loans, corrections, and perks.

ENHANCED VERSION: Comprehensive keyword matching with detailed categorization
and breakdown reporting for accurate revenue calculation.
"""
import re
from typing import Dict, Iterable, List, Optional, Tuple


OWNER_OR_BUSINESS_HINTS = [
    "sneads",
    "snead",
]

DEDUCTION_RULES = [
    (
        "Financing & Loans",
        [
            # Advances
            r"\badvances?\b",
            r"\badvance\s+(?:payment|deposit|credit)\b",
            r"\bcash\s+advance\b",
            r"\bmerchant\s+advance\b",
            
            # Lines of Credit
            r"\bloc\b",
            r"\bline\s+of\s+credit\b",
            r"\bolb\b",
            r"\bocc\b",
            r"\bcredit\s+line\b",
            
            # Loans
            r"\bloan\b",
            r"\bloans?\s+(?:deposit|proceeds|disbursement)\b",
            r"\blender\b",
            r"\blending\b",
            r"\bfinancing\b",
            
            # Equipment Finance
            r"\bequipment\s+finance\b",
            r"\bequipment\s+lease\b",
            r"\bequipment\s+loan\b",
            r"\bnextgear\b",
            r"\bcashflow\s+funding\b",
            r"\basset\s+lease\b",
            r"\basset\s+financing\b",
            r"\bvehicle\s+financing\b",
            r"\bauto\s+loan\b",
            
            # Personal Loans
            r"\bpersonal\s+loans?\b",
            r"\bconsumer\s+loan\b",
            
            # Overdraft
            r"\boverdraft\b",
            r"\bod\s+(?:protection|transfer|deposit)\b",
            r"\bnsf\s+(?:protection|coverage)\b",
            
            # Provisional/Temporary Credits
            r"\bprovisional\s+credit\b",
            r"\btemporary\s+credit\b",
            r"\bpending\s+credit\b",
            r"\bconditional\s+credit\b",
        ],
    ),
    (
        "Internal Transfers & Linked Accounts",
        [
            # Account-to-Account Transfers
            r"\ba2a\b",
            r"\baccount\s+to\s+account\b",
            r"\bacct\s+to\s+acct\b",
            
            # Cash Management
            r"\bcash\s*m(?:ana)?g?m?nt\b",
            r"\bcash\s+management\s+(?:transfer|sweep)\b",
            
            # Transfer Keywords
            r"\bcol\s+xfer\b",
            r"\bdeposit\s+transfer\b",
            r"\bfunds?\s+transfers?\b",
            r"\btransfer(?:s|red|ring)?\b",
            r"\bxfr\b",
            r"\bxfer\b",
            r"\btfr\b",
            r"\btransferred\s+from\b",
            
            # Account Number References
            r"\bfrom\s+(?:acct|account)\s*(?:x+|\*+|#)?\d{3,}\b",
            r"\b(?:acct|account)\s*(?:x+|\*+|#)?\d{3,}\b",
            r"\bfrom\s+account\s+ending\s+in\s+\d{4}\b",
            
            # Account Types
            r"\bpayroll\s+account\b",
            r"\bfrom\s+(?:chk|checking|savings|mma|payroll)\b",
            r"\bfrom\s+(?:checking|savings)\s+(?:account|acct)\b",
            r"\bsavings\s+transfer\b",
            r"\bchecking\s+transfer\b",
            
            # Online/Mobile Banking
            r"\bmobile\s+banking\s+transfer\b",
            r"\bonline\s+banking\s+transfer\b",
            r"\bonline\s+xfer\b",
            r"\bonline\s+transfer\b",
            r"\bweb\s+transfer\b",
            r"\binternet\s+banking\s+transfer\b",
            r"\bpc\s+transfer\b",
            r"\bpc\s+banking\b",
            
            # Telephone Banking
            r"\btelephone\s+transfer\b",
            r"\btele\s+transfer\b",
            r"\bphone\s+transfer\b",
            
            # Third-Party Apps
            r"\bacorns\b",
            r"\bvenmo\b",
            r"\bzelle\b",
            r"\bcash\s+app\b",
            r"\bpaypal\s+transfer\b",
            
            # Money Transfer
            r"\bmoney\s+transfer\b",
            r"\binternal\s+transfer\b",
            r"\bowner\s+transfer\b",
            r"\bbusiness\s+transfer\b",
        ],
    ),
    (
        "Banking Corrections, Reversals & Perks",
        [
            # Adjustments
            r"\bcredit\s+adjust(?:ment)?\b",
            r"\bwithdrawal\s+adjustment\b",
            r"\bdebit\s+adjustment\b",
            r"\badjustment\b",
            
            # Corrections
            r"\bdebit\s+card\s+credit\s+voucher\b",
            r"\bdeposit\s+correction\b",
            r"\bshare\s+draft\s+correction\b",
            r"\berror\s+deposit\b",
            r"\berror\s+correction\b",
            r"\bmisposted\b",
            r"\bcorrection\b",
            
            # NSF & Returns
            r"\bnsf\b",
            r"\bnon[\s-]?sufficient\s+funds\b",
            r"\breturns?\b",
            r"\brtn\b",
            r"\bret\b",
            r"\breturned\s+(?:item|check|deposit)\b",
            r"\bitem\s+returned\b",
            
            # Rewards & Perks
            r"\bcash\s*back\b",
            r"\brewards?\b",
            r"\brebates?\b",
            r"\brbt\b",
            r"\bpoints\s+redemption\b",
            r"\bcredit\s+card\s+rewards\b",
            
            # Interest & Dividends
            r"\bdividends?\b",
            r"\binterest\b",
            r"\binterest\s+(?:earned|paid|credit)\b",
            r"\bdividend\s+(?:payment|credit)\b",
            
            # Refunds
            r"\brefunds?\b",
            r"\brefunded\b",
            r"\bmerchant\s+refund\b",
            r"\breturn\s+refund\b",
            
            # Treasury & Government
            r"\btreas(?:ury)?\b",
            r"\btreasury\s+(?:payment|deposit)\b",
            r"\birs\s+refund\b",
            r"\btax\s+refund\b",
            
            # Vouchers & Fees
            r"\bvouchers?\b",
            r"\bfees?\s+(?:reversal|refund|credit)\b",
            r"\bfee\s+reversal\b",
            r"\bfee\s+waiver\b",
            
            # Trial/Verification Deposits
            r"\btrial\s+deposit\b",
            r"\bverify\s+deposit\b",
            r"\bverification\s+deposit\b",
            r"\bmicro[\s-]?deposit\b",
        ],
    ),
]

# WIRE DEPOSIT CONDITIONAL RULES

WIRE_DEDUCTION_PATTERNS = [
    r"\bmerchant\b",
    r"\bmerchant['']?s\b",
    r"\bloc\b",
    r"\bline\s+of\s+credit\b",
    r"\blender\b",
    r"\bloan\b",
    r"\bfunding\b",
    r"\bfinance\b",
    r"\bfinancing\b",
    r"\badvance\b",
]



# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def _normalise(text: str) -> str:
    """Normalize text for pattern matching."""
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _first_rule_match(text: str, rules: Iterable[tuple]) -> Optional[Tuple[str, str]]:
    """
    Find the first matching rule from the deduction rules.
    Returns (category, pattern) or None.
    """
    for category, patterns in rules:
        for pattern in patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return (category, pattern)
    return None



# CLASSIFICATION FUNCTIONS


def classify_credit_revenue(
    description: str,
    *,
    account_holder: Optional[str] = None,
    business_name: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """
    Return revenue status metadata for a credit transaction.

    Returns:
        {
            "status": "revenue" | "deduction",
            "reason": category name or None,
            "rule": matched pattern or None,
        }

    Rules:
    1. Check for owner/business authorized transfers first
    2. Apply special wire deposit conditional logic
    3. Check against comprehensive deduction rules
    4. Default to revenue if no match
    """
    text = _normalise(description)
    if not text:
        return {
            "status": "revenue",
            "reason": None,
            "rule": None,
        }

    # ── Rule 1: Owner/Business Authorized Transfers ──
    owner_hints = [account_holder, business_name, *OWNER_OR_BUSINESS_HINTS]
    for hint in owner_hints:
        hint_norm = _normalise(hint or "")
        if hint_norm and hint_norm in text:
            # Check if it's an authorized money transfer
            if re.search(r"\bmoney\s+transfer\b|\bauth(?:orized)?\b", text, re.IGNORECASE):
                return {
                    "status": "deduction",
                    "reason": "Internal Transfers & Linked Accounts",
                    "rule": "owner/business authorized money transfer",
                }

    # ── Rule 2: Special Conditional Rule for Wire Deposits ──
    if re.search(r"\bwire\b", text, re.IGNORECASE):
        # Check if wire is from merchant, lender, or LOC
        for pattern in WIRE_DEDUCTION_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return {
                    "status": "deduction",
                    "reason": "Special Conditional Rule: Wire Deposits",
                    "rule": f"wire from {pattern}",
                }
        # Standard business wire - keep as revenue
        return {
            "status": "revenue",
            "reason": None,
            "rule": "standard business wire kept as revenue",
        }

    # ── Rule 3: Check Comprehensive Deduction Rules ──
    matched = _first_rule_match(text, DEDUCTION_RULES)
    if matched:
        category, pattern = matched
        return {
            "status": "deduction",
            "reason": category,
            "rule": pattern,
        }

    # ── Default: Accept as Revenue ──
    return {
        "status": "revenue",
        "reason": None,
        "rule": None,
    }

def apply_revenue_filter(
    transactions: List,
    *,
    account_holder: Optional[str] = None,
    business_name: Optional[str] = None,
) -> Dict:
    """
    Apply revenue filtering to all transactions and generate detailed breakdown.

    Returns:
        {
            "raw_credits": total credit amount,
            "adjusted_revenue": revenue after deductions,
            "revenue_deductions": total deducted amount,
            "total_debits": total debit amount,
            "deduction_breakdown": {category: amount},
            "revenue_transactions": count,
            "deduction_transactions": count,
        }
    """
    raw_credits = 0.0
    adjusted_revenue = 0.0
    revenue_deductions = 0.0
    total_debits = 0.0
    
    # Track deductions by category
    deduction_breakdown: Dict[str, float] = {}
    revenue_count = 0
    deduction_count = 0

    for transaction in transactions:
        credit = float(transaction.credit or 0)
        debit = float(transaction.debit or 0)
        total_debits += debit

        # Handle non-credit transactions
        if credit <= 0:
            transaction.transaction_type = "debit" if debit > 0 else "unknown"
            transaction.revenue_status = None
            transaction.revenue_deduction_reason = None
            transaction.revenue_rule = None
            transaction.adjusted_revenue_amount = None
            continue

        # Process credit transactions
        raw_credits += credit
        classification = classify_credit_revenue(
            transaction.description,
            account_holder=account_holder,
            business_name=business_name,
        )
        
        transaction.transaction_type = "credit"
        transaction.revenue_status = classification["status"]
        transaction.revenue_deduction_reason = classification["reason"]
        transaction.revenue_rule = classification["rule"]

        if classification["status"] == "deduction":
            # This is a non-revenue deposit
            revenue_deductions += credit
            transaction.adjusted_revenue_amount = 0.0
            deduction_count += 1
            
            # Track by category
            category = classification["reason"] or "Other Deductions"
            deduction_breakdown[category] = deduction_breakdown.get(category, 0.0) + credit
        else:
            # This is true operational revenue
            adjusted_revenue += credit
            transaction.adjusted_revenue_amount = credit
            revenue_count += 1

    return {
        "raw_credits": round(raw_credits, 2),
        "adjusted_revenue": round(adjusted_revenue, 2),
        "revenue_deductions": round(revenue_deductions, 2),
        "total_debits": round(total_debits, 2),
        "deduction_breakdown": {
            k: round(v, 2) for k, v in deduction_breakdown.items()
        },
        "revenue_transactions": revenue_count,
        "deduction_transactions": deduction_count,
    }

def generate_revenue_breakdown_report(
    transactions: List,
    revenue_snapshot: Dict,
) -> str:
    """
    Generate a detailed human-readable breakdown report.
    
    Format:
    ┌─────────────────────────────────────────────────────────────┐
    │ REVENUE BREAKDOWN SUMMARY                                   │
    ├─────────────────────────────────────────────────────────────┤
    │ Raw Credits (All Deposits):              $XX,XXX.XX         │
    │ Less: Revenue Deductions:               ($X,XXX.XX)         │
    │ ─────────────────────────────────────────────────────────── │
    │ Adjusted Revenue (True Operations):      $XX,XXX.XX         │
    └─────────────────────────────────────────────────────────────┘
    """
    lines = []
    lines.append("=" * 70)
    lines.append("REVENUE BREAKDOWN SUMMARY")
    lines.append("=" * 70)
    lines.append("")
    
    # Summary Section
    raw = revenue_snapshot["raw_credits"]
    deductions = revenue_snapshot["revenue_deductions"]
    adjusted = revenue_snapshot["adjusted_revenue"]
    
    lines.append(f"Raw Credits (All Deposits):          ${raw:>15,.2f}")
    lines.append(f"Less: Revenue Deductions:           (${deductions:>15,.2f})")
    lines.append("-" * 70)
    lines.append(f"Adjusted Revenue (True Operations):  ${adjusted:>15,.2f}")
    lines.append("")
    
    # Deduction Breakdown by Category
    if revenue_snapshot.get("deduction_breakdown"):
        lines.append("=" * 70)
        lines.append("DEDUCTION BREAKDOWN BY CATEGORY")
        lines.append("=" * 70)
        lines.append("")
        
        for category, amount in sorted(
            revenue_snapshot["deduction_breakdown"].items(),
            key=lambda x: x[1],
            reverse=True
        ):
            lines.append(f"  {category:<50} ${amount:>12,.2f}")
        lines.append("")
    
    # Transaction Counts
    lines.append("=" * 70)
    lines.append("TRANSACTION COUNTS")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"  Revenue Transactions:     {revenue_snapshot.get('revenue_transactions', 0):>6}")
    lines.append(f"  Deduction Transactions:   {revenue_snapshot.get('deduction_transactions', 0):>6}")
    lines.append(f"  Total Credit Transactions: {revenue_snapshot.get('revenue_transactions', 0) + revenue_snapshot.get('deduction_transactions', 0):>6}")
    lines.append("")
    
    # Itemized Credits
    lines.append("=" * 70)
    lines.append("ITEMIZED CREDITS BREAKDOWN")
    lines.append("=" * 70)
    lines.append("")
    
    for txn in transactions:
        if txn.credit and txn.credit > 0:
            status_icon = "✓" if txn.revenue_status == "revenue" else "✗"
            amount_str = f"${txn.credit:,.2f}"
            
            if txn.revenue_status == "deduction":
                reason = txn.revenue_deduction_reason or "Other"
                lines.append(f"{status_icon} [{reason}]")
                lines.append(f"   {txn.date or 'N/A':<12} {amount_str:>12}  {txn.description[:60]}")
            else:
                lines.append(f"{status_icon} [REVENUE]")
                lines.append(f"   {txn.date or 'N/A':<12} {amount_str:>12}  {txn.description[:60]}")
            lines.append("")
    
    # Debits Summary
    lines.append("=" * 70)
    lines.append("DEBITS SUMMARY")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"Total Debits (Outgoing):             ${revenue_snapshot['total_debits']:>15,.2f}")
    lines.append("")
    
    return "\n".join(lines)
