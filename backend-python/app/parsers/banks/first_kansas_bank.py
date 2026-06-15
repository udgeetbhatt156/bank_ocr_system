"""First Kansas Bank statement parser.

Handles First Kansas Bank business checking statements with:
- Separate DEPOSITS and WITHDRAWALS sections (not a unified table)
- No running balance column in either section
- Daily balances in a separate table at the end of the statement
- Trailing minus sign on debit amounts (e.g. "225.46-")
- M/DD date format with OCR-introduced spacing (e.g. "8 / 0 1")
- Multi-line descriptions (3-4 lines per transaction)
- Deposit slip image pages at end (to skip)
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from app.models.schemas import Transaction
from app.parsers.base import BaseParser
from app.parsers.registry import register_parser, register_template_parser
from app.parsers.result import ParseResult, StatementMetadata
from app.services.amount_utils import clean_amount
from app.services.date_utils import parse_date
from app.services.postprocessor import calculate_confidence

_BANK_ID = "FIRST_KANSAS_BANK"
_BANK_NAME = "First Kansas Bank"
_TEMPLATE_ID = "first_kansas_bank_v1"

# Date pattern: handles OCR-spaced dates like "8 / 0 1" or normal "8/01"
_DATE_LINE_RE = re.compile(
    r"^\s*(?P<month>\d{1,2})\s*/\s*(?P<day>\d\s*\d)\s+(?P<rest>.+)$"
)

# Money pattern: matches amounts like "225.46-", "2,850.00", ".07", ".11", "16,225.00"
_MONEY_RE = re.compile(r"\$?\s*\d[\d,]*\.\d{2}-?|\.\d{2}-?")

# Page header noise to skip
_PAGE_HEADER_RE = re.compile(
    r"^Date\s+\d{1,2}/\d{2}/\d{2,4}\s+Page\s+\d+|"
    r"^ALL SEASONS|"
    r"^\d{4}\s+\w+\s+ST|"
    r"^HAYS KS|"
    r"^Business Checking\s+\w+\s+\(Continued\)|"
    r"^D\s*A\s*T\s*E\s+DESCRIPTION\s+AMOUNT|"
    r"^Primary Account|"
    r"^Enclosures\s+\d+|"
    r"^___+",
    re.IGNORECASE,
)

# Section markers
_DEPOSITS_HEADER_RE = re.compile(r"^\s*DEPOSITS\s*$", re.IGNORECASE)
_WITHDRAWALS_HEADER_RE = re.compile(r"^\s*WITHDRAWALS\s*$", re.IGNORECASE)
_DAILY_BALANCE_RE = re.compile(r"DAILY\s+BALANCE\s+INFORMATION", re.IGNORECASE)

# Deposit slip page marker (pages to skip)
_DEPOSIT_SLIP_RE = re.compile(r"Deposit/Credit\s+Date:", re.IGNORECASE)


class FirstKansasBankParser(BaseParser):
    """Parser for First Kansas Bank business checking statements."""

    parser_id = _TEMPLATE_ID

    # ── public API ──────────────────────────────────────────────────

    def extract_metadata(self) -> StatementMetadata:
        """Extract statement-level metadata from page 1 summary block."""
        return self._extract_metadata()

    def extract_transactions(self) -> List[Transaction]:
        """Extract and merge deposits + withdrawals in chronological order."""
        deposits, withdrawals = self._parse_sections()
        return self._merge_chronologically(deposits, withdrawals)

    def parse(self) -> ParseResult:
        """Parse statement and return full result with validation."""
        metadata = self._extract_metadata()
        deposits, withdrawals = self._parse_sections()
        transactions = self._merge_chronologically(deposits, withdrawals)
        daily_balances = self._extract_daily_balances()
        validation_errors = self._validate(metadata, transactions)

        # Build structured output matching Timberland/Forbright pattern
        structured_transactions = []
        for idx, txn in enumerate(transactions, start=1):
            is_debit = txn.debit is not None
            structured_transactions.append({
                "seq": idx,
                "date": txn.date,
                "description": txn.description,
                "type": "debit" if is_debit else "credit",
                "credit": txn.credit,
                "debit": txn.debit,
                "running_balance": None,
            })

        return ParseResult(
            metadata=metadata,
            transactions=transactions,
            confidence=calculate_confidence([txn.dict() for txn in transactions]),
            parser_id=self.parser_id,
            bank_id=_BANK_ID,
            template_id=self.context.template_id or _TEMPLATE_ID,
            validation_errors=validation_errors,
            extra={
                "first_kansas_bank_output": {
                    "bank_name": _BANK_NAME,
                    "account_holder": {
                        "name": metadata.customer_name,
                        "address": metadata.customer_address,
                    },
                    "account_type": metadata.account_type,
                    "account_number": metadata.account_number,
                    "statement_period": {
                        "start_date": metadata.statement_start_date,
                        "end_date": metadata.statement_end_date,
                        "statement_date": metadata.statement_date,
                    },
                    "summary_financials": {
                        "previous_balance": metadata.opening_balance,
                        "ending_balance": metadata.closing_balance,
                        "total_deposits_credits": metadata.total_credits,
                        "deposit_credit_count": metadata.credit_count,
                        "total_checks_debits": metadata.total_debits,
                        "check_debit_count": metadata.debit_count,
                        "service_charge": metadata.service_charge,
                        "interest_earned": getattr(metadata, "_interest_earned", None),
                        "average_balance": getattr(metadata, "_average_balance", None),
                    },
                    "transactions": structured_transactions,
                    "daily_balances": daily_balances,
                    "fee_summary": {
                        "overdraft_fees_this_period": metadata.overdraft_fees_this_period,
                        "overdraft_fees_ytd": metadata.overdraft_fees_ytd,
                        "returned_item_fees_this_period": metadata.returned_item_fees_this_period,
                    },
                },
            },
        )

    # ── metadata extraction ─────────────────────────────────────────

    def _extract_metadata(self) -> StatementMetadata:
        text = self._text()
        lines = self._lines()

        customer_name = self._extract_customer_name(lines)
        customer_address = self._extract_customer_address(lines)
        account_number = self._extract_account_number(text)
        account_type = self._extract_account_type(text)
        statement_date = self._extract_statement_date(text)
        period_start, period_end = self._extract_period(text)
        number_of_days = self._extract_int(text, r"#\s*OF\s*DAYS[-\s]*STMT\s*PERIOD\s+(\d+)")
        previous_balance = self._extract_amount(text, r"P\s*R\s*E\s*V\s*I\s*O\s*U\s*S\s+BALANCE\s+([\d,.]+)")
        ending_balance = self._extract_amount(text, r"E\s*N\s*D\s*I\s*N\s*G\s+BALANCE\s+([\d,.]+)")
        average_balance = self._extract_amount(text, r"AVERAGE\s+BALANCE\s+([\d,.]+)")
        service_charge = self._extract_amount(text, r"T\s*O\s*T\s*A\s*L\s+SRV\s+CHG\s+TODAY\s+([\d,.]+)")
        interest_earned = self._extract_amount(text, r"Interest\s+Earned\s+([\d,.]+)")

        # Deposits/Credits count and amount: "1 0 DEPOSITS/CREDITS 29,230.32"
        # OCR may space digits: "1 0" for 10, "1 0 4" for 104
        credit_count, total_credits = self._extract_spaced_count_and_amount(
            text, r"DEPOSITS?/CREDITS?"
        )
        # Checks/Debits count and amount: "1 0 4 CHECKS/DEBITS 12,996.37"
        debit_count, total_debits = self._extract_spaced_count_and_amount(
            text, r"CHECKS?/DEBITS?"
        )

        # Fee table: TOTAL OVERDRAFT FEES | $.00 | $35.00
        overdraft_period = self._extract_fee(text, r"T\s*O\s*T\s*A\s*L\s+OVERDRAFT\s+FEES\s*\|?\s*\$?([\d,.]+)")
        overdraft_ytd = self._extract_second_fee(text, r"T\s*O\s*T\s*A\s*L\s+OVERDRAFT\s+FEES.*?\$?[\d,.]+.*?\$?([\d,.]+)")
        returned_period = self._extract_fee(text, r"T\s*O\s*T\s*A\s*L\s+RETURNED\s+ITEM\s+FEES\s*\|?\s*\$?([\d,.]+)")

        # YTD Interest and APY
        ytd_interest = self._extract_amount(text, r"\d{4}\s+Interest\s+Paid\s+([\d,.]+)")
        apy = None
        m_apy = re.search(r"Annual\s+Percentage\s+Yield\s+Earned\s+([\d.]+%)", text, re.IGNORECASE)
        if m_apy:
            apy = m_apy.group(1)

        metadata = StatementMetadata(
            bank_id=_BANK_ID,
            bank_name=_BANK_NAME,
            account_number=account_number,
            customer_name=customer_name,
            customer_address=customer_address,
            account_type=account_type,
            statement_date=statement_date,
            statement_start_date=period_start,
            statement_end_date=period_end,
            opening_balance=previous_balance,
            closing_balance=ending_balance,
            current_balance=ending_balance,
            total_credits=total_credits,
            credit_count=credit_count,
            total_debits=total_debits,
            debit_count=debit_count,
            service_charge=service_charge,
            overdraft_fees_this_period=overdraft_period,
            overdraft_fees_ytd=overdraft_ytd,
            returned_item_fees_this_period=returned_period,
        )

        # Stash extra fields that don't fit in StatementMetadata
        metadata._interest_earned = interest_earned
        metadata._average_balance = average_balance
        metadata._annual_pct_yield = apy
        metadata._ytd_interest_paid = ytd_interest
        metadata._number_of_days = number_of_days

        return metadata

    def _extract_customer_name(self, lines: List[str]) -> Optional[str]:
        """Extract customer/business name from header block."""
        for line in lines[:10]:
            # Look for the business name line (not bank header / page info)
            if "LLC" in line.upper() or "INC" in line.upper() or "CORP" in line.upper():
                # Clean up — take just the name part before "Primary Account"
                name = re.split(r"\s+Primary\s+Account", line, flags=re.IGNORECASE)[0].strip()
                if name:
                    return name
        # Fallback: second non-empty line often has the name
        non_empty = [l.strip() for l in lines[:5] if l.strip() and not l.strip().startswith("Date")]
        if non_empty:
            name = re.split(r"\s+Primary\s+Account", non_empty[0], flags=re.IGNORECASE)[0].strip()
            return name
        return None

    def _extract_customer_address(self, lines: List[str]) -> Optional[str]:
        """Extract customer address block (lines between name and separator)."""
        address_parts = []
        capture = False
        for line in lines[:10]:
            cleaned = line.strip()
            if not cleaned:
                continue
            # Start capturing after the customer name line
            if ("LLC" in cleaned.upper() or "INC" in cleaned.upper()) and not capture:
                capture = True
                continue
            if capture:
                # Stop at separator or account info
                if cleaned.startswith("_") or "Account Number" in cleaned or "Type of Account" in cleaned:
                    break
                # Clean out "Enclosures X" suffix
                addr = re.sub(r"\s+Enclosures\s+\d+", "", cleaned, flags=re.IGNORECASE).strip()
                if addr:
                    address_parts.append(addr)
        return " ".join(address_parts) if address_parts else None

    def _extract_account_number(self, text: str) -> Optional[str]:
        """Extract account number from various patterns."""
        # Pattern: "Primary Account XXXXXXXX8677"
        m = re.search(r"Primary\s+Account\s+([Xx\d]+)", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        # Pattern: "ACCOUNT NO XXXXXXXX8677"
        m = re.search(r"A\s*C\s*C\s*O\s*U\s*N\s*T\s+NO\s+([Xx\d]+)", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return None

    def _extract_account_type(self, text: str) -> Optional[str]:
        m = re.search(r"(Business\s+Checking|Personal\s+Checking|Savings)", text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_statement_date(self, text: str) -> Optional[str]:
        """Extract top-right statement date: 'Date 8/29/25'."""
        m = re.search(r"Date\s+(\d{1,2}/\d{1,2}/\d{2,4})", text, re.IGNORECASE)
        if m:
            return parse_date(m.group(1), statement_year=self._statement_year())
        return None

    def _extract_period(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract statement period: 'Statement Dates 8/01/25 thru 9/01/25'."""
        m = re.search(
            r"Statement\s+Dates?\s+(\d{1,2}/\d{1,2}/\d{2,4})\s+thru\s+(\d{1,2}/\d{1,2}/\d{2,4})",
            text,
            re.IGNORECASE,
        )
        if m:
            year = self._statement_year()
            return (
                parse_date(m.group(1), statement_year=year),
                parse_date(m.group(2), statement_year=year),
            )
        return None, None

    # ── section parsing ─────────────────────────────────────────────

    def _parse_sections(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Parse DEPOSITS and WITHDRAWALS sections into separate lists.

        Returns:
            (deposits, withdrawals) — each is a list of dicts with
            keys: date, description, amount
        """
        deposits: List[Dict[str, Any]] = []
        withdrawals: List[Dict[str, Any]] = []
        section: Optional[str] = None  # "DEPOSITS" or "WITHDRAWALS"
        current_txn: Optional[Dict[str, Any]] = None

        def flush():
            nonlocal current_txn
            if current_txn is None:
                return
            # Finalize description
            desc = " ".join(current_txn["desc_parts"])
            desc = re.sub(r"\s+", " ", desc).strip()
            # Remove " / " separators (join multi-line with space)
            desc = desc.replace(" / ", " ")
            current_txn["description"] = desc

            if current_txn["section"] == "DEPOSITS":
                deposits.append(current_txn)
            elif current_txn["section"] == "WITHDRAWALS":
                withdrawals.append(current_txn)
            current_txn = None

        lines = self._lines()
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Check for deposit slip pages — stop processing
            if _DEPOSIT_SLIP_RE.search(stripped):
                flush()
                break

            # Check for daily balance section — stop transaction parsing
            if _DAILY_BALANCE_RE.search(stripped):
                flush()
                break

            # Detect section headers
            # When re-entering the same section on a continued page,
            # do NOT flush: continuation lines at the top of the new
            # page belong to the last transaction from the previous page.
            if _DEPOSITS_HEADER_RE.match(stripped):
                if section != "DEPOSITS":
                    flush()
                section = "DEPOSITS"
                continue
            if _WITHDRAWALS_HEADER_RE.match(stripped):
                if section != "WITHDRAWALS":
                    flush()
                section = "WITHDRAWALS"
                continue

            # Skip non-transaction content
            if section is None:
                continue
            if self._is_page_noise(stripped):
                continue

            # Try to parse a date-starting line (new transaction)
            date_match = self._parse_date_line(stripped)
            if date_match:
                flush()
                date_str, rest = date_match
                parsed_date = self._normalize_date(date_str)
                if parsed_date is None:
                    # Not a valid date — treat as continuation
                    if current_txn:
                        current_txn["desc_parts"].append(stripped)
                    continue

                # Extract amount from the rest of the line
                amount = self._extract_line_amount(rest)
                desc_text = self._remove_amount_from_text(rest) if amount is not None else rest

                current_txn = {
                    "date": parsed_date,
                    "section": section,
                    "amount": abs(amount) if amount is not None else None,
                    "desc_parts": [desc_text] if desc_text.strip() else [],
                }
                continue

            # Continuation line (no date)
            if current_txn is not None:
                # Check if this line has an amount (e.g. amount on continuation)
                amount_match = list(_MONEY_RE.finditer(stripped))
                if amount_match and current_txn["amount"] is None:
                    # This continuation line has the amount
                    amount_raw = amount_match[-1].group()
                    val = clean_amount(amount_raw)
                    if val is not None:
                        current_txn["amount"] = abs(val)
                        desc_text = stripped[:amount_match[-1].start()].strip()
                        if desc_text:
                            current_txn["desc_parts"].append(desc_text)
                    else:
                        current_txn["desc_parts"].append(stripped)
                else:
                    current_txn["desc_parts"].append(stripped)

        flush()

        # Filter out entries without amounts
        deposits = [d for d in deposits if d.get("amount") is not None]
        withdrawals = [w for w in withdrawals if w.get("amount") is not None]

        return deposits, withdrawals

    def _merge_chronologically(
        self,
        deposits: List[Dict[str, Any]],
        withdrawals: List[Dict[str, Any]],
    ) -> List[Transaction]:
        """Merge deposits and withdrawals in chronological order."""
        all_txns = []

        for dep in deposits:
            all_txns.append(Transaction(
                date=dep["date"],
                description=dep["description"],
                credit=dep["amount"],
                debit=None,
                balance=None,
            ))

        for wd in withdrawals:
            all_txns.append(Transaction(
                date=wd["date"],
                description=wd["description"],
                credit=None,
                debit=wd["amount"],
                balance=None,
            ))

        # Sort by date, then credits before debits for same date
        all_txns.sort(key=lambda t: (t.date or "", 0 if t.credit else 1))
        return all_txns

    # ── daily balance extraction ────────────────────────────────────

    def _extract_daily_balances(self) -> List[Dict[str, Any]]:
        """Extract the daily balance table from the end of the statement."""
        balances: List[Dict[str, Any]] = []
        in_daily_balance = False

        for line in self._lines():
            if _DAILY_BALANCE_RE.search(line):
                in_daily_balance = True
                continue
            if not in_daily_balance:
                continue

            # Skip the header line "D A T E  BALANCE  DATE  BALANCE  DATE  BALANCE"
            if re.search(r"D\s*A\s*T\s*E\s+BALANCE", line, re.IGNORECASE):
                continue

            # Stop at deposit slip pages or end of data
            if _DEPOSIT_SLIP_RE.search(line):
                break
            if re.search(r"Deposit/Credit", line, re.IGNORECASE):
                break

            # Parse date-balance pairs: "8 / 0 1 619.97 8/13 2,746.77 8/25 4,676.68"
            # First clean OCR spacing in dates
            cleaned = self._collapse_spaced_date(line)

            # Find all date-balance pairs
            for m in re.finditer(
                r"(\d{1,2}/\d{1,2})\s+([\d,]+\.\d{2}|-?\.\d{2})",
                cleaned,
            ):
                date_str = m.group(1)
                bal_str = m.group(2)
                parsed_date = self._normalize_date(date_str)
                bal_val = clean_amount(bal_str)
                if parsed_date and bal_val is not None:
                    balances.append({
                        "date": parsed_date,
                        "balance": bal_val,
                    })

        return balances

    # ── validation ──────────────────────────────────────────────────

    def _validate(
        self,
        metadata: StatementMetadata,
        transactions: List[Transaction],
    ) -> List[str]:
        errors: List[str] = []

        credit_sum = round(sum(float(t.credit or 0) for t in transactions), 2)
        debit_sum = round(sum(float(t.debit or 0) for t in transactions), 2)
        credit_count = sum(1 for t in transactions if t.credit is not None)
        debit_count = sum(1 for t in transactions if t.debit is not None)

        # First Kansas Bank lists Interest Deposit in the DEPOSITS section,
        # but the statement's reported count/total EXCLUDES it (interest is
        # reported separately in the summary).  We account for this by
        # subtracting the interest amount from our extracted credit total
        # before comparing against the statement.
        interest_amount = getattr(metadata, "_interest_earned", None) or 0.0
        interest_txn_count = sum(
            1 for t in transactions
            if t.credit is not None and "interest" in (t.description or "").lower()
        )

        adjusted_credit_sum = round(credit_sum - interest_amount, 2)
        adjusted_credit_count = credit_count - interest_txn_count

        # Count validation (adjusted for interest)
        if metadata.credit_count is not None and metadata.credit_count != adjusted_credit_count:
            errors.append(
                f"Credit count mismatch: extracted {adjusted_credit_count} "
                f"(+{interest_txn_count} interest), statement says {metadata.credit_count}."
            )
        if metadata.debit_count is not None and metadata.debit_count != debit_count:
            errors.append(
                f"Debit count mismatch: extracted {debit_count}, statement says {metadata.debit_count}."
            )

        # Total validation (adjusted for interest)
        if metadata.total_credits is not None and abs(adjusted_credit_sum - metadata.total_credits) > 0.05:
            errors.append(
                f"Credit total mismatch: extracted {adjusted_credit_sum} "
                f"(+{interest_amount} interest), statement says {metadata.total_credits}."
            )
        if metadata.total_debits is not None and abs(debit_sum - metadata.total_debits) > 0.05:
            errors.append(
                f"Debit total mismatch: extracted {debit_sum}, statement says {metadata.total_debits}."
            )

        # Balance reconciliation using ACTUAL extracted totals (including interest)
        # This should balance: opening + all_credits - all_debits = closing
        if (
            metadata.opening_balance is not None
            and metadata.closing_balance is not None
        ):
            expected_closing = round(
                metadata.opening_balance + credit_sum - debit_sum, 2
            )
            if abs(expected_closing - metadata.closing_balance) > 0.05:
                errors.append(
                    f"Balance reconciliation failed: "
                    f"Start={metadata.opening_balance} + Credits={credit_sum} "
                    f"- Debits={debit_sum} = {expected_closing}, "
                    f"Expected End={metadata.closing_balance}"
                )

        return errors

    # ── helpers ──────────────────────────────────────────────────────

    def _lines(self) -> List[str]:
        """Get all lines from raw text or rows."""
        if self.context.raw_text:
            return [line for line in self.context.raw_text.splitlines() if line.strip()]
        return [
            " ".join(str(cell) for cell in row if str(cell).strip()).strip()
            for row in self.context.rows
            if row and any(str(cell).strip() for cell in row)
        ]

    def _text(self) -> str:
        if self.context.raw_text:
            return self.context.raw_text
        return "\n".join(self._lines())

    def _statement_year(self) -> int:
        if self.context.statement_year:
            return self.context.statement_year
        # Try to find from statement text
        text = self._text()
        m = re.search(r"Date\s+\d{1,2}/\d{1,2}/(\d{2,4})", text)
        if m:
            yr = int(m.group(1))
            return yr if yr > 99 else 2000 + yr
        return 2025

    def _parse_date_line(self, line: str) -> Optional[Tuple[str, str]]:
        """Parse a line starting with a date. Returns (date_str, rest) or None.

        Handles OCR-spaced dates like '8 / 0 1' and normal dates like '8/01'.
        """
        m = _DATE_LINE_RE.match(line)
        if m:
            month = m.group("month").strip()
            day = m.group("day").replace(" ", "").strip()
            date_str = f"{month}/{day}"
            return date_str, m.group("rest").strip()
        return None

    def _normalize_date(self, raw: str) -> Optional[str]:
        """Normalize M/DD date to ISO format using statement year."""
        # Strip any OCR spacing
        raw = raw.replace(" ", "")
        return parse_date(raw, statement_year=self._statement_year())

    def _collapse_spaced_date(self, text: str) -> str:
        """Collapse OCR-spaced dates like '8 / 0 1' into '8/01'."""
        return re.sub(
            r"(\d{1,2})\s*/\s*(\d)\s*(\d)",
            lambda m: f"{m.group(1)}/{m.group(2)}{m.group(3)}",
            text,
        )

    def _extract_line_amount(self, text: str) -> Optional[float]:
        """Extract the last monetary amount from a text string."""
        matches = list(_MONEY_RE.finditer(text))
        if not matches:
            return None
        raw = matches[-1].group().strip()
        return clean_amount(raw)

    def _remove_amount_from_text(self, text: str) -> str:
        """Remove the last monetary amount from text to get the description."""
        matches = list(_MONEY_RE.finditer(text))
        if not matches:
            return text
        last = matches[-1]
        return (text[:last.start()] + text[last.end():]).strip()

    def _is_page_noise(self, line: str) -> bool:
        """Check if a line is page header/footer noise to skip."""
        if _PAGE_HEADER_RE.match(line):
            return True
        return False

    def _extract_amount(self, text: str, pattern: str) -> Optional[float]:
        """Extract a single amount using a regex pattern."""
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return clean_amount(m.group(1))
        return None

    def _extract_int(self, text: str, pattern: str) -> Optional[int]:
        """Extract an integer using a regex pattern."""
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except (ValueError, IndexError):
                pass
        return None

    def _extract_count_and_amount(
        self, text: str, pattern: str
    ) -> Tuple[Optional[int], Optional[float]]:
        """Extract a count and amount from a pattern like '10 DEPOSITS/CREDITS 29,230.32'."""
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            count = int(m.group(1))
            amount = clean_amount(m.group(2))
            return count, amount
        return None, None

    def _extract_fee(self, text: str, pattern: str) -> Optional[float]:
        """Extract a fee amount."""
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return clean_amount(m.group(1))
        return None

    def _extract_second_fee(self, text: str, pattern: str) -> Optional[float]:
        """Extract the second fee amount (YTD) from fee table row."""
        m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if m:
            return clean_amount(m.group(1))
        return None

    def _extract_spaced_count_and_amount(
        self, text: str, label_pattern: str
    ) -> Tuple[Optional[int], Optional[float]]:
        """Extract count and amount where count digits may be OCR-spaced.

        Handles patterns like:
          '1 0 DEPOSITS/CREDITS 29,230.32'   → count=10, amount=29230.32
          '1 0 4 CHECKS/DEBITS 12,996.37'    → count=104, amount=12996.37

        Uses MULTILINE mode with ^ anchor to prevent matching across lines.
        """
        m = re.search(
            rf"^[\s]*(\d[\d ]{{0,8}})\s+{label_pattern}\s+([\d,.]+)",
            text,
            re.IGNORECASE | re.MULTILINE,
        )
        if m:
            count_str = m.group(1).replace(" ", "")
            count = int(count_str) if count_str.isdigit() else None
            amount = clean_amount(m.group(2))
            return count, amount
        return None, None


register_parser(_BANK_ID, FirstKansasBankParser)
register_parser("FIRST_KANSAS", FirstKansasBankParser)
register_parser("FIRST_KANSAS_BANK", FirstKansasBankParser)
register_template_parser(_TEMPLATE_ID, FirstKansasBankParser)
