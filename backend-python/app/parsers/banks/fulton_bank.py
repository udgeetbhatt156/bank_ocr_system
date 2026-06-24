"""Fulton Bank, N.A. statement parser.

Handles Business Checking / Deposit Statement PDFs (form code DEPSTMT).
Uses raw-text line-by-line parsing with balance-delta credit/debit classification.
"""

import re
from typing import Any, Dict, List, Optional

from app.models.schemas import Transaction
from app.parsers.base import BaseParser
from app.parsers.registry import register_parser, register_template_parser
from app.parsers.result import ParseResult, StatementMetadata
from app.services.date_utils import parse_date
from app.services.postprocessor import calculate_confidence

# ── Bank identification markers ──────────────────────────────────────────────
_DETECTION_PATTERNS = [
    re.compile(r"Fulton\s*Bank,?\s*N\.?A\.?\s*Member\s*FDIC", re.IGNORECASE),
    re.compile(r"fultonbank\.com", re.IGNORECASE),
    re.compile(r"Deposit\s+Support\s+PM", re.IGNORECASE),
    re.compile(r"P\.?O\.?\s*Box\s*4887", re.IGNORECASE),
    re.compile(r"DEPSTMT", re.IGNORECASE),
]

# ── Metadata extraction ─────────────────────────────────────────────────────
_STMT_DATE_RE = re.compile(
    r"Statement\s+Date:\s*(\d{2}/\d{2}/\d{2})\s+through\s+(\d{2}/\d{2}/\d{2})",
    re.IGNORECASE,
)
_PRIMARY_ACCT_RE = re.compile(r"Primary\s+Account:\s*(X{3,4}\d{4})", re.IGNORECASE)
_ACCT_TYPE_RE = re.compile(r"(BUSINESS\s+CHECKING)\s+Account\s+(X{3,4}\d{4})", re.IGNORECASE)
_CUSTOMER_NAME_RE = re.compile(
    r"Account\s+Statement\s*\n\s*([A-Z][A-Z0-9 &.,'-]+(?:LLC|INC|CORP|LP|LLP|GROUP)?)\s*\n",
    re.IGNORECASE | re.MULTILINE,
)

# Summary block
_PRIOR_BAL_RE = re.compile(r"Prior\s+Statement\s+Balance", re.IGNORECASE)
_TOTAL_DEPOSITS_RE = re.compile(r"Total\s+Deposits/Credits", re.IGNORECASE)
_TOTAL_DEBITS_RE = re.compile(r"Total\s+Checks/Debits", re.IGNORECASE)
_ENDING_BAL_LABEL_RE = re.compile(r"Ending\s+Statement\s+Balance", re.IGNORECASE)
_CURRENCY_RE = re.compile(r"-?\$?([\d,]+\.\d{2})")

# Fees
_OD_FEE_RE = re.compile(
    r"Total\s+Overdraft/OD\s+Fees\s+\(Paid\s+Items\)\s+\$?([\d,]+\.\d{2})\s+\$?([\d,]+\.\d{2})",
    re.IGNORECASE,
)
_NSF_FEE_RE = re.compile(
    r"Total\s+Non-Sufficient\s+Funds/NSF\s+Fees\s+\(Returned\s+Items?\)\s+\$?([\d,]+\.\d{2})\s+\$?([\d,]+\.\d{2})",
    re.IGNORECASE,
)
_TOTAL_SVC_FEES_RE = re.compile(r"Total\s+Service\s+Fees\s+\$?([\d,]+\.\d{2})", re.IGNORECASE)

# ── Transaction line parsing ─────────────────────────────────────────────────
# Primary transaction line: date + description + up to 3 trailing numbers
_TXN_LINE_RE = re.compile(
    r"^(\d{2}/\d{2})\s+"                         # date MM/DD
    r"(.+?)\s+"                                    # description (non-greedy)
    r"(-?[\d,]+\.\d{2})\s+"                        # amount1 (amount or balance)
    r"(-?[\d,]+\.\d{2})"                           # amount2 (balance)
    r"\s*$"
)
# Transaction line with only balance (sentinel rows like ENDING BALANCE FROM PRIOR STATEMENT)
_TXN_BALANCE_ONLY_RE = re.compile(
    r"^(\d{2}/\d{2})\s+"                           # date
    r"(.+?)\s+"                                    # description
    r"(-?[\d,]+\.\d{2})"                           # single trailing number = balance
    r"\s*$"
)
# Sub-description / reference lines (indented, no leading date)
_SUB_LINE_RE = re.compile(r"^\s*([A-Za-z0-9 .,&*#'\-/()]+)\s*$")
# Date prefix detector
_DATE_PREFIX_RE = re.compile(r"^\d{2}/\d{2}\s+")

# Check summary
_CHECK_ROW_RE = re.compile(r"(\d{5})\s*(\*)?\s+(\d{2}/\d{2})\s+([\d,]+\.\d{2})")
_TOTAL_CHECKS_COUNT_RE = re.compile(r"Total\s+Number\s+of\s+Checks\s+(\d+)", re.IGNORECASE)
_TOTAL_CHECKS_AMOUNT_RE = re.compile(r"Total\s+Amount\s+of\s+Checks\s+\$?([\d,]+\.\d{2})", re.IGNORECASE)

# Lines to skip (page furniture / boilerplate)
_SKIP_PATTERNS = [
    re.compile(r"^3100110330", re.IGNORECASE),
    re.compile(r"^Page\s+\d+\s+of\s+\d+", re.IGNORECASE),
    re.compile(r"^Deposit\s+Support\s+PM", re.IGNORECASE),
    re.compile(r"^P\.?O\.?\s*Box\s*4887", re.IGNORECASE),
    re.compile(r"^Lancaster,\s*PA", re.IGNORECASE),
    re.compile(r"^Statement\s+Date:", re.IGNORECASE),
    re.compile(r"^Primary\s+Account:", re.IGNORECASE),
    re.compile(r"^For\s+information\s+regarding", re.IGNORECASE),
    re.compile(r"^please\s+call\s+Customer", re.IGNORECASE),
    re.compile(r"^Account\s+Statement$", re.IGNORECASE),
    re.compile(r"^Account\s+Activity$", re.IGNORECASE),
    re.compile(r"^Date\s+Description\s+Deposits", re.IGNORECASE),
    re.compile(r"^fultonbank\.com", re.IGNORECASE),
    re.compile(r"^Fulton\s+Bank,?\s*N\.?A", re.IGNORECASE),
    re.compile(r"^DEPSTMT", re.IGNORECASE),
    re.compile(r"^Deposit\s+Statement$", re.IGNORECASE),
    re.compile(r"^Rev\.\s+\d{2}/\d{2}/\d{4}", re.IGNORECASE),
    re.compile(r"^RECONCILEMENT\s+FORM", re.IGNORECASE),
]

# Section boundaries — stop parsing Account Activity at these
_STOP_SECTIONS = [
    re.compile(r"^Check\s+Summary", re.IGNORECASE),
    re.compile(r"^Interest\s+Earned\s+Information", re.IGNORECASE),
    re.compile(r"^Service\s+Fee\s+Balance", re.IGNORECASE),
    re.compile(r"^Service\s+Fee\s+Disclosure", re.IGNORECASE),
    re.compile(r"^Service\s+Fees$", re.IGNORECASE),
    re.compile(r"^Overdraft\s+Elect", re.IGNORECASE),
    re.compile(r"^\*Overdrafts\s+may\s+be", re.IGNORECASE),
]


def _parse_amount(raw: str) -> float:
    """Parse a currency string like '1,136.91' or '-5,192.00' into float."""
    s = raw.strip().replace(",", "").replace("$", "")
    negative = s.startswith("-")
    s = s.lstrip("-")
    value = float(s) if s else 0.0
    return -value if negative else value


def _is_skip_line(line: str) -> bool:
    """Return True if the line is page furniture / boilerplate."""
    stripped = line.strip()
    if not stripped:
        return True
    for pat in _SKIP_PATTERNS:
        if pat.search(stripped):
            return True
    return False


def _is_stop_section(line: str) -> bool:
    """Return True if we've hit a non-transaction section."""
    stripped = line.strip()
    for pat in _STOP_SECTIONS:
        if pat.search(stripped):
            return True
    return False


class FultonBankParser(BaseParser):
    parser_id = "fulton_bank"

    def _raw_text(self) -> str:
        """Get the raw text from context."""
        if hasattr(self.context, "raw_text") and self.context.raw_text:
            return self.context.raw_text
        # Fallback: reconstruct from rows
        return "\n".join(" ".join(str(c) for c in row) for row in self.context.rows)

    def extract_metadata(self) -> StatementMetadata:
        text = self._raw_text()

        # ── Detection confidence ──
        score = 0
        for pat in _DETECTION_PATTERNS:
            if pat.search(text):
                score += 20

        # ── Statement dates ──
        statement_start = None
        statement_end = None
        m = _STMT_DATE_RE.search(text)
        if m:
            statement_start = parse_date(m.group(1))
            statement_end = parse_date(m.group(2))

        # ── Account info ──
        account_number = None
        m = _PRIMARY_ACCT_RE.search(text)
        if m:
            account_number = m.group(1)

        account_type = None
        m = _ACCT_TYPE_RE.search(text)
        if m:
            account_type = m.group(1).strip()
            if not account_number:
                account_number = m.group(2)

        # ── Customer name ──
        customer_name = None
        m = _CUSTOMER_NAME_RE.search(text)
        if m:
            customer_name = m.group(1).strip()

        # ── Summary balances ──
        # Extract from rows (reliable since pdfplumber gives clean table rows)
        opening_balance = None
        closing_balance = None
        total_credits = None
        total_debits = None

        for i, row in enumerate(self.context.rows):
            row_text = " ".join(str(c) for c in row).lower()
            if "prior statement balance" in row_text and i + 1 < len(self.context.rows):
                val_row = self.context.rows[i + 1]
                amounts = []
                for cell in val_row:
                    m_amt = _CURRENCY_RE.search(str(cell))
                    if m_amt:
                        amounts.append(_parse_amount(m_amt.group(0)))
                if len(amounts) >= 4:
                    opening_balance = amounts[0]
                    total_credits = amounts[1]
                    total_debits = amounts[2]
                    closing_balance = amounts[3]
                elif len(amounts) >= 2:
                    opening_balance = amounts[0]
                    closing_balance = amounts[-1]
                break

        # ── Fee extraction ──
        service_charge = None
        m = _TOTAL_SVC_FEES_RE.search(text)
        if m:
            service_charge = _parse_amount(m.group(1))

        od_fees_period = None
        od_fees_ytd = None
        m = _OD_FEE_RE.search(text)
        if m:
            od_fees_period = _parse_amount(m.group(1))
            od_fees_ytd = _parse_amount(m.group(2))

        nsf_fees_period = None
        nsf_fees_ytd = None
        m = _NSF_FEE_RE.search(text)
        if m:
            nsf_fees_period = _parse_amount(m.group(1))
            nsf_fees_ytd = _parse_amount(m.group(2))

        return StatementMetadata(
            bank_id="fulton_bank",
            bank_name="Fulton Bank, N.A.",
            account_number=account_number,
            account_holder=customer_name,
            customer_name=customer_name,
            account_type=account_type,
            statement_start_date=statement_start,
            statement_end_date=statement_end,
            opening_balance=opening_balance,
            closing_balance=closing_balance,
            current_balance=closing_balance,
            total_credits=total_credits,
            total_debits=total_debits,
            service_charge=service_charge,
            overdraft_fees_this_period=od_fees_period,
            overdraft_fees_ytd=od_fees_ytd,
            returned_item_fees_this_period=nsf_fees_period,
            returned_item_fees_ytd=nsf_fees_ytd,
        )

    def extract_transactions(self) -> List[Transaction]:
        text = self._raw_text()
        lines = text.split("\n")
        stmt_year = self.context.statement_year

        # ── Collect raw transaction records ──
        # Each record: (date_str, description, trailing_numbers[], sub_lines[])
        records: List[Dict[str, Any]] = []
        current_record: Optional[Dict[str, Any]] = None
        in_activity = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Start of Account Activity section
            if re.match(r"^Date\s+Description\s+Deposits", stripped, re.IGNORECASE):
                in_activity = True
                continue

            if not in_activity:
                continue

            # Stop at non-transaction sections
            if _is_stop_section(stripped):
                break

            # Skip page furniture
            if _is_skip_line(stripped):
                # Re-enter activity mode after page break headers
                if re.match(r"^Account\s+Activity$", stripped, re.IGNORECASE):
                    in_activity = True
                continue

            # Re-detect activity header on continuation pages
            if re.match(r"^Date\s+Description\s+Deposits", stripped, re.IGNORECASE):
                continue

            # Try to match a primary transaction line (date + desc + 2 numbers)
            m_txn = _TXN_LINE_RE.match(stripped)
            if m_txn:
                # Save previous record
                if current_record:
                    records.append(current_record)
                current_record = {
                    "date": m_txn.group(1),
                    "description": m_txn.group(2).strip(),
                    "amount": _parse_amount(m_txn.group(3)),
                    "balance": _parse_amount(m_txn.group(4)),
                    "sub_lines": [],
                }
                continue

            # Try balance-only line (sentinel rows)
            m_bal = _TXN_BALANCE_ONLY_RE.match(stripped)
            if m_bal:
                if current_record:
                    records.append(current_record)
                current_record = {
                    "date": m_bal.group(1),
                    "description": m_bal.group(2).strip(),
                    "amount": None,  # No transaction amount
                    "balance": _parse_amount(m_bal.group(3)),
                    "sub_lines": [],
                }
                continue

            # Sub-line (payee name, trace/reference)
            if current_record and not _DATE_PREFIX_RE.match(stripped):
                if _SUB_LINE_RE.match(stripped):
                    current_record["sub_lines"].append(stripped.strip())
                continue

        # Don't forget the last record
        if current_record:
            records.append(current_record)

        # ── Convert records to Transaction objects ──
        transactions: List[Transaction] = []
        prev_balance: Optional[float] = None

        for rec in records:
            date_str = parse_date(rec["date"], statement_year=stmt_year)
            desc = rec["description"]
            amount = rec["amount"]
            balance = rec["balance"]

            # Skip sentinel rows
            if "ENDING BALANCE FROM PRIOR STATEMENT" in desc.upper():
                prev_balance = balance
                continue
            if desc.upper().strip() == "ENDING BALANCE":
                prev_balance = balance
                continue

            # Append sub-lines to description
            if rec["sub_lines"]:
                desc = desc + " " + " ".join(rec["sub_lines"])

            # Determine credit vs debit via balance-delta
            credit = None
            debit = None

            if amount is not None:
                if prev_balance is not None and balance is not None:
                    delta = round(balance - prev_balance, 2)
                    if delta > 0:
                        credit = abs(amount)
                    else:
                        debit = abs(amount)
                else:
                    # Fallback: no previous balance context yet
                    # Assume positive delta = credit (first transaction after opening)
                    credit = abs(amount)

            prev_balance = balance

            transactions.append(Transaction(
                date=date_str,
                description=desc,
                debit=debit,
                credit=credit,
                balance=balance,
            ))

        return transactions

    def parse(self) -> ParseResult:
        metadata = self.extract_metadata()
        transactions = self.extract_transactions()

        # ── Check summary cross-validation ──
        text = self._raw_text()
        checks_register: List[Dict[str, Any]] = []
        validation_errors: List[str] = []

        for m in _CHECK_ROW_RE.finditer(text):
            check_no = m.group(1)
            out_of_seq = m.group(2) == "*"
            check_date = parse_date(m.group(3), statement_year=self.context.statement_year)
            check_amount = _parse_amount(m.group(4))
            checks_register.append({
                "check_no": check_no,
                "out_of_sequence": out_of_seq,
                "date": check_date,
                "amount": check_amount,
            })

        # Validate check count
        m_count = _TOTAL_CHECKS_COUNT_RE.search(text)
        if m_count:
            expected_count = int(m_count.group(1))
            if len(checks_register) != expected_count:
                validation_errors.append(
                    f"Check count mismatch: summary says {expected_count}, parsed {len(checks_register)}"
                )

        # Validate check total
        m_total = _TOTAL_CHECKS_AMOUNT_RE.search(text)
        if m_total:
            expected_total = _parse_amount(m_total.group(1))
            actual_total = sum(c["amount"] for c in checks_register)
            if abs(actual_total - expected_total) > 0.05:
                validation_errors.append(
                    f"Check total mismatch: summary ${expected_total:.2f}, parsed ${actual_total:.2f}"
                )

        # Cross-validate checks against transaction entries
        check_txns = [t for t in transactions if "CHECK #" in (t.description or "").upper()]
        for chk in checks_register:
            found = any(
                chk["check_no"] in (t.description or "")
                and chk["date"] == str(t.date)
                for t in check_txns
            )
            if not found:
                validation_errors.append(
                    f"Check #{chk['check_no']} from summary not found in transactions"
                )

        confidence = calculate_confidence([t.dict() for t in transactions])

        return ParseResult(
            metadata=metadata,
            transactions=transactions,
            confidence=confidence,
            parser_id=self.parser_id,
            bank_id=metadata.bank_id,
            template_id="fulton_bank_business_checking_v1",
            checks_register=checks_register,
            validation_errors=validation_errors,
            skip_deduplication=True,
        )


# ── Register the parser ──────────────────────────────────────────────────────
register_parser("FULTON_BANK", FultonBankParser)
register_template_parser("fulton_bank_business_checking_v1", FultonBankParser)
