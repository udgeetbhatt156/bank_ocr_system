"""Palmetto State Bank parser."""

import re
from typing import List, Optional, Tuple

from app.models.schemas import Transaction
from app.parsers.base import BaseParser
from app.parsers.result import ParseResult, StatementMetadata
from app.parsers.registry import register_parser, register_template_parser
from app.services.amount_utils import clean_amount
from app.services.date_utils import parse_date
from app.services.metadata_extractor import extract_statement_metadata
from app.services.postprocessor import calculate_confidence


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_BANK_NAME = "Palmetto State Bank"
_BANK_ID = "PALMETTO_STATE_BANK"
_TEMPLATE_ID = "palmetto_state_bank_v1"

# Header line that marks the start of the transaction table on every page
_TABLE_HEADER_RE = re.compile(
    r"(?:DESCRIPTION|DEBITS|DATE).{5,40}BALANCE",
    re.IGNORECASE,
)

# Stop-parsing sentinels
_TABLE_END_RE = re.compile(
    r"BALANCE\s+THIS\s+STATEMENT"
    r"|TOTAL\s+DAYS\s+IN\s+STATEMENT\s+PERIOD"
    r"|YOUR\s+CHECKS\s+SEQUENCED",
    re.IGNORECASE,
)

# "* * * C O N T I N U E D * * *" — end of page, more data follows
_CONTINUED_RE = re.compile(r"\*\s*\*\s*\*\s*C\s*O\s*N\s*T\s*I\s*N\s*U\s*E\s*D", re.IGNORECASE)

# Opening-balance line
_OPENING_BAL_RE = re.compile(
    r"BALANCE\s+LAST\s+STATEMENT\s*\.+\s*"
    r"(\d{1,2}/\d{1,2}/\d{2,4})\s+"
    r"([\d,]+\.\d{2})",
    re.IGNORECASE,
)

# Closing-balance line
_CLOSING_BAL_RE = re.compile(
    r"BALANCE\s+THIS\s+STATEMENT\s*\.+\s*"
    r"(\d{1,2}/\d{1,2}/\d{2,4})\s+"
    r"([\d,]+\.\d{2})",
    re.IGNORECASE,
)

# Account number + statement-end date from page header
# e.g. "ACCOUNT:    84014753  12/15/2025"
_ACCOUNT_HEADER_RE = re.compile(
    r"ACCOUNT\s*:?\s*(\d{6,12})\s+(\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE,
)

# Summary totals
_TOTAL_CREDITS_RE = re.compile(
    r"TOTAL\s+CREDITS\s*\(\s*(\d+)\s*\)\s*([\d,]+\.\d{2})",
    re.IGNORECASE,
)
_TOTAL_DEBITS_RE = re.compile(
    r"TOTAL\s+DEBITS\s*\(\s*(\d+)\s*\)\s*([\d,]+\.\d{2})",
    re.IGNORECASE,
)

_CREDIT_DESCRIPTION_RE = re.compile(
    r"\b(REPRESENTMENT|AFFIRM\.COM\s+PAYME|DEPOSIT|CREDIT)\b",
    re.IGNORECASE,
)

_DEBIT_DESCRIPTION_RE = re.compile(
    r"\b("
    r"EXPANSIONCAP\s+(?:PMTS|FEE)|INTUIT\s+\d+\s+TRAN\s+FEE|"
    r"XX\d{4}\s+(?:PURCHASE|ATM\s+WITHDRAWAL)|"
    r"\d{6,}\s+TRANSFER\s+TO\s+X{2,}\d+|"
    r"CAPITAL\s+ONE\s+(?:CRCARDPMT|MOBILE\s+PMT)|"
    r"ALLY\s+ALLY\s+PAYMT|CHECK"
    r")\b",
    re.IGNORECASE,
)

# A data line has at least a DATE column value (MM/DD/YY) somewhere to the right
# and ends with a BALANCE figure.
# We treat any line that contains a date-like token + at least one amount as a data line.
_DATA_LINE_RE = re.compile(
    r"(\d{1,2}/\d{1,2}/\d{2,4})\s+([\(+\-]?\$?[\d,]+\.\d{2}\)?)(?:\s*|\s+[^0-9a-zA-Z]*)$"
)

# Blocklisted strings that must never be used as customer_name
_CUSTOMER_NAME_BLOCKLIST = re.compile(
    r"palmetto\s+state\s+bank|palmetto|state\s+bank|palmetto\s+checking\s+account",
    re.IGNORECASE,
)

# Column x-anchor ranges (character offsets within a fixed-width text line).
# These match the template spec:  DEBITS ~40-52 | CREDITS ~53-62 | DATE ~63-72 | BALANCE ~73-82
_COL_DEBIT_START = 38
_COL_DEBIT_END = 53
_COL_CREDIT_START = 53
_COL_CREDIT_END = 63
_COL_DATE_START = 63
_COL_DATE_END = 73
_COL_BALANCE_START = 73
_COL_BALANCE_END = 90  # generous right margin


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flatten_rows(rows: List[List]) -> List[str]:
    """Convert the 2-D cell grid into a flat list of non-empty text lines."""
    lines: List[str] = []
    for row in rows:
        if not row:
            continue
        line = " ".join(str(c) for c in row if str(c).strip()).strip()
        if line:
            lines.append(line)
    return lines


def _pad_line(line: str, width: int = 100) -> str:
    """Right-pad a line to `width` characters so column slicing is safe."""
    return line.ljust(width)


def _slice_col(line: str, start: int, end: int) -> str:
    """Extract and strip a column slice from a fixed-width line."""
    padded = _pad_line(line)
    return padded[start:end].strip()


def _extract_amount(text: str) -> Optional[float]:
    """Parse a numeric amount string like '1,234.56' into a float."""
    if not text:
        return None
    cleaned = str(text).strip()
    negative = (
        cleaned.startswith("(") and cleaned.endswith(")")
    ) or cleaned.endswith("-") or cleaned.startswith("-")
    cleaned = re.sub(r"[,$()\s-]", "", cleaned)
    try:
        value = float(cleaned)
        return -value if negative else value
    except ValueError:
        return None


def _is_data_line(line: str) -> bool:
    """Return True if the line looks like a transaction data line.

    A data line contains a date token (MM/DD/YY or MM/DD/YYYY) AND ends with
    a balance figure.
    """
    return bool(_DATA_LINE_RE.search(line))


def _parse_data_line(line: str, statement_year: Optional[int] = None) -> Tuple[
    Optional[str],      # date
    Optional[float],    # debit
    Optional[float],    # credit
    Optional[float],    # balance
]:
    """Extract (date, debit, credit, balance) from a Palmetto data line.

    Strategy:
      1. Try fixed-column slices (most reliable for digital PDFs).
      2. Fall back to right-anchored regex parsing.
    """
    # --- Fixed-column slice attempt ---
    date_str_raw = _slice_col(line, _COL_DATE_START, _COL_DATE_END)
    debit_raw = _slice_col(line, _COL_DEBIT_START, _COL_DEBIT_END)
    credit_raw = _slice_col(line, _COL_CREDIT_START, _COL_CREDIT_END)
    balance_raw = _slice_col(line, _COL_BALANCE_START, _COL_BALANCE_END)

    date_val = parse_date(date_str_raw, statement_year=statement_year) if date_str_raw else None
    debit_val = _extract_amount(debit_raw) if debit_raw else None
    credit_val = _extract_amount(credit_raw) if credit_raw else None
    balance_val = _extract_amount(balance_raw) if balance_raw else None

    if date_val and balance_val is not None:
        return date_val, debit_val, credit_val, balance_val

    # --- Regex fallback: right-anchored ---
    # Pattern: ... [optional debit] [optional credit]  DATE  BALANCE
    m = re.search(
        r"(?:([\(+\-]?\$?[\d,]+\.\d{2}\)?)\s+)?"   # optional debit or credit (first amount)
        r"(?:([\(+\-]?\$?[\d,]+\.\d{2}\)?)\s+)?"   # optional second amount
        r"(\d{1,2}/\d{1,2}/\d{2,4})\s+"            # date
        r"([\(+\-]?\$?[\d,]+\.\d{2}\)?)(?:\s*|\s+[^0-9a-zA-Z]*)$",  # balance
        line,
    )
    if not m:
        return None, None, None, None

    date_val = parse_date(m.group(3), statement_year=statement_year)
    balance_val = _extract_amount(m.group(4))
    amt1 = _extract_amount(m.group(1)) if m.group(1) else None
    amt2 = _extract_amount(m.group(2)) if m.group(2) else None

    # Determine debit vs credit from column position of the matched amount
    # by comparing match positions against the column anchors.
    if amt2 is not None:
        # Two amounts before the date → amt1=debit, amt2=credit (rare but possible)
        debit_val = amt1
        credit_val = amt2
    elif amt1 is not None:
        # Single amount — decide by its position in the line
        match_start = m.start(1)
        if match_start < _COL_CREDIT_START:
            debit_val = amt1
            credit_val = None
        else:
            debit_val = None
            credit_val = amt1
    else:
        debit_val = None
        credit_val = None

    return date_val, debit_val, credit_val, balance_val


def _apply_description_direction(
    description: str,
    debit: Optional[float],
    credit: Optional[float],
) -> Tuple[Optional[float], Optional[float]]:
    """Use Palmetto-specific description clues when OCR column spacing is weak."""
    amount: Optional[float] = None
    if debit is not None and credit is None:
        amount = abs(debit)
    elif credit is not None and debit is None:
        amount = abs(credit)
    else:
        return debit, credit

    if _CREDIT_DESCRIPTION_RE.search(description):
        return None, amount
    if _DEBIT_DESCRIPTION_RE.search(description):
        return amount, None
    return debit, credit


class PalmettoStateBankParser(BaseParser):
    """Parser for Palmetto State Bank fixed-width / scanned-OCR statements."""

    parser_id = _TEMPLATE_ID
    def extract_metadata(self) -> StatementMetadata:
        transactions = self.extract_transactions()
        return self._extract_palmetto_metadata(transactions)

    def extract_transactions(self) -> List[Transaction]:
        lines = _flatten_rows(self.context.rows)
        return self._parse_transactions(lines, statement_year=self.context.statement_year)

    def parse(self) -> ParseResult:
        transactions = self.extract_transactions()
        metadata = self._extract_palmetto_metadata(transactions)
        validation_errors = self._validate(metadata, transactions)
        return ParseResult(
            metadata=metadata,
            transactions=transactions,
            confidence=calculate_confidence([txn.dict() for txn in transactions]),
            parser_id=self.parser_id,
            bank_id=metadata.bank_id,
            template_id=self.context.template_id,
            validation_errors=validation_errors,
        )

    # ------------------------------------------------------------------
    # Metadata extraction
    # ------------------------------------------------------------------

    def _extract_palmetto_metadata(
        self,
        transactions: List[Transaction],
    ) -> StatementMetadata:

        fallback = extract_statement_metadata(self.context.rows, transactions)
        lines = _flatten_rows(self.context.rows)
        full_text = "\n".join(lines)

        # --- Account number & statement end date ---
        account_number: Optional[str] = fallback.get("account_number")
        statement_end_date: Optional[str] = None

        for line in lines:
            m = _ACCOUNT_HEADER_RE.search(line)
            if m:
                account_number = m.group(1).strip()
                statement_end_date = parse_date(
                    m.group(2), statement_year=self.context.statement_year
                )
                break

        # --- Opening balance & statement start date ---
        opening_balance: Optional[float] = None
        statement_start_date: Optional[str] = None

        for line in lines:
            m = _OPENING_BAL_RE.search(line)
            if m:
                statement_start_date = parse_date(
                    m.group(1), statement_year=self.context.statement_year
                )
                opening_balance = _extract_amount(m.group(2))
                break

        # --- Closing balance ---
        closing_balance: Optional[float] = None

        for line in lines:
            m = _CLOSING_BAL_RE.search(line)
            if m:
                closing_balance = _extract_amount(m.group(2))
                break

        # Fall back to last transaction balance
        if closing_balance is None:
            balances = [t.balance for t in transactions if t.balance is not None]
            if balances:
                closing_balance = balances[-1]

        # --- Summary totals ---
        total_credits_count: Optional[int] = None
        total_credits_amount: Optional[float] = None
        total_debits_count: Optional[int] = None
        total_debits_amount: Optional[float] = None

        m = _TOTAL_CREDITS_RE.search(full_text)
        if m:
            total_credits_count = int(m.group(1))
            total_credits_amount = _extract_amount(m.group(2))

        m = _TOTAL_DEBITS_RE.search(full_text)
        if m:
            total_debits_count = int(m.group(1))
            total_debits_amount = _extract_amount(m.group(2))

        # --- Customer name & account name (page 1 only) ---
        fallback_customer_name: Optional[str] = fallback.get("customer_name")
        customer_name, account_name = self._extract_names(lines)
        if not customer_name:
            customer_name = fallback_customer_name

        return StatementMetadata(
            bank_id=_BANK_ID,
            bank_name=_BANK_NAME,
            account_number=account_number,
            account_type="Checking",
            customer_name=customer_name,
            account_holder=account_name or customer_name,
            statement_start_date=statement_start_date,
            statement_end_date=statement_end_date,
            opening_balance=opening_balance,
            current_balance=closing_balance,
            closing_balance=closing_balance,
            credit_count=total_credits_count,
            total_credits=total_credits_amount,
            debit_count=total_debits_count,
            total_debits=total_debits_amount,
        )

    def _extract_names(
        self, lines: List[str]
    ) -> Tuple[Optional[str], Optional[str]]:
        """Extract customer_name (personal) and account_name (business) from page 1.

        The template specifies a 4-line centered address block on page 1:
          Line 1: Business name   (account_name)
          Line 2: Personal name   (customer_name)
          Line 3: Street address
          Line 4: City, State ZIP

        Heuristic: scan the first 30 lines for an ALL-CAPS name that is NOT
        blocklisted, preceded or followed by a street/address line.
        """
        customer_name: Optional[str] = None
        account_name: Optional[str] = None

        # Only look at the first page (~first 40 lines)
        page1_lines = lines[:40]

        anchored_account, anchored_customer = self._extract_names_from_logo_block(
            page1_lines
        )
        if anchored_account or anchored_customer:
            return anchored_customer or anchored_account, anchored_account

        # Find a line that looks like a US street address as an anchor
        address_re = re.compile(
            r"\d+\s+[A-Z0-9 .]+\s+(?:ST|AVE|RD|DR|LN|BLVD|WAY|CT|HWY|ROUTE|RTE|PO BOX)",
            re.IGNORECASE,
        )
        city_state_zip_re = re.compile(
            r"[A-Z][A-Za-z\s]+,\s*[A-Z]{2}\s+\d{5}",
            re.IGNORECASE,
        )

        address_idx: Optional[int] = None
        for idx, line in enumerate(page1_lines):
            if address_re.search(line) or city_state_zip_re.search(line):
                address_idx = idx
                break

        if address_idx is not None and address_idx >= 2:
            # Lines immediately before the address are the name block
            # Line at address_idx - 2 → business name
            # Line at address_idx - 1 → personal name  (may be absent)
            candidate_business = page1_lines[address_idx - 2].strip()
            candidate_person = page1_lines[address_idx - 1].strip()

            # Validate business name: ALL-CAPS, not blocklisted, not an address
            if (
                candidate_business
                and candidate_business == candidate_business.upper()
                and not _CUSTOMER_NAME_BLOCKLIST.search(candidate_business)
                and not address_re.search(candidate_business)
            ):
                account_name = candidate_business

            # Validate personal name: ALL-CAPS, looks like a name (letters + dots/spaces)
            if (
                candidate_person
                and re.match(r"^[A-Z][A-Z.\s]+$", candidate_person)
                and not _CUSTOMER_NAME_BLOCKLIST.search(candidate_person)
                and not address_re.search(candidate_person)
            ):
                customer_name = candidate_person
            else:
                # Fallback: use business name as customer name
                customer_name = account_name

        # Last-resort: scan for any ALL-CAPS two-word name on page 1
        if not customer_name:
            for line in page1_lines:
                line = line.strip()
                if (
                    re.match(r"^[A-Z][A-Z.\s]{4,40}$", line)
                    and not _CUSTOMER_NAME_BLOCKLIST.search(line)
                    and not address_re.search(line)
                    and len(line.split()) >= 2
                ):
                    customer_name = line
                    break

        return customer_name, account_name

    def _extract_names_from_logo_block(
        self, lines: List[str]
    ) -> Tuple[Optional[str], Optional[str]]:
        """Use the Palmetto logo URL block when OCR preserves page-one order."""
        start_idx: Optional[int] = None
        for idx, line in enumerate(lines):
            if "palmettostatebanksc.com" in line.lower():
                start_idx = idx + 1
                break
        if start_idx is None:
            return None, None

        candidates: List[str] = []
        for line in lines[start_idx : start_idx + 10]:
            stripped = line.strip()
            if not stripped:
                continue
            if re.search(r"={5,}", stripped):
                break
            if _CUSTOMER_NAME_BLOCKLIST.search(stripped):
                continue
            if re.search(
                r"\b(DESCRIPTION|DEBITS|CREDITS|DATE|BALANCE|PAGE|ACCOUNT)\b",
                stripped,
                re.IGNORECASE,
            ):
                continue
            if re.search(r"\d{5}(?:-\d{4})?$", stripped):
                continue
            if re.match(r"^\d+\s+", stripped):
                continue
            candidates.append(stripped)
            if len(candidates) >= 2:
                break

        account_name = candidates[0] if candidates else None
        customer_name = candidates[1] if len(candidates) > 1 else None
        return account_name, customer_name

    def _validate(
        self,
        metadata: StatementMetadata,
        transactions: List[Transaction],
    ) -> List[str]:
        errors: List[str] = []
        credit_sum = round(sum(float(txn.credit or 0) for txn in transactions), 2)
        debit_sum = round(sum(float(txn.debit or 0) for txn in transactions), 2)
        credit_count = sum(1 for txn in transactions if txn.credit is not None)
        debit_count = sum(1 for txn in transactions if txn.debit is not None)

        if metadata.credit_count and metadata.credit_count != credit_count:
            errors.append(
                f"Credit count mismatch: extracted "
                f"{credit_count}, statement says {metadata.credit_count}."
            )
        if metadata.debit_count and metadata.debit_count != debit_count:
            errors.append(
                f"Debit count mismatch: extracted "
                f"{debit_count}, statement says {metadata.debit_count}."
            )

        if (
            metadata.total_credits is not None
            and abs(credit_sum - metadata.total_credits) > 0.05
        ):
            errors.append(
                f"Credit total mismatch: extracted {credit_sum}, "
                f"statement says {metadata.total_credits}."
            )
        if (
            metadata.total_debits is not None
            and abs(debit_sum - metadata.total_debits) > 0.05
        ):
            errors.append(
                f"Debit total mismatch: extracted {debit_sum}, "
                f"statement says {metadata.total_debits}."
            )
        if (
            metadata.opening_balance is not None
            and metadata.closing_balance is not None
            and metadata.total_credits is not None
            and metadata.total_debits is not None
        ):
            expected = round(
                metadata.opening_balance + metadata.total_credits - metadata.total_debits,
                2,
            )
            if abs(expected - metadata.closing_balance) > 0.05:
                errors.append(
                    f"Balance equation failed: {metadata.opening_balance} + "
                    f"{metadata.total_credits} - {metadata.total_debits} = "
                    f"{expected}, statement says {metadata.closing_balance}."
                )

        return errors

    # ------------------------------------------------------------------
    # Transaction extraction
    # ------------------------------------------------------------------

    def _parse_transactions(
        self,
        lines: List[str],
        statement_year: Optional[int] = None,
    ) -> List[Transaction]:
        """State-machine parser for Palmetto's two-part transaction rows.

        Each transaction is:
          PART A: 1–3 description lines (left-aligned text, no amounts)
          PART B: data line with [DEBIT] [CREDIT] DATE  BALANCE
        """
        transactions: List[Transaction] = []
        in_table: bool = False
        desc_buffer: List[str] = []
        seq: int = 0

        def flush_buffer_without_data() -> None:
            """Discard any buffered description lines that never got a data line."""
            desc_buffer.clear()

        def commit_transaction(
            date_str: str,
            debit: Optional[float],
            credit: Optional[float],
            balance: Optional[float],
        ) -> None:
            nonlocal seq
            description = " ".join(desc_buffer).strip()
            desc_buffer.clear()

            if not description:
                return
            # Skip the opening balance pseudo-transaction
            if re.search(r"BALANCE\s+LAST\s+STATEMENT", description, re.IGNORECASE):
                return

            debit, credit = _apply_description_direction(description, debit, credit)

            seq += 1
            transactions.append(
                Transaction(
                    seq=seq,
                    date=date_str,
                    description=description,
                    debit=debit,
                    credit=credit,
                    balance=balance,
                )
            )

        for line in lines:
            # ---- Detect table header ----
            if _TABLE_HEADER_RE.search(line):
                in_table = True
                flush_buffer_without_data()
                continue

            # ---- Stop markers ----
            if _TABLE_END_RE.search(line):
                flush_buffer_without_data()
                in_table = False
                continue

            # "* * * CONTINUED * * *" — page break, table resumes on next page
            if _CONTINUED_RE.search(line):
                flush_buffer_without_data()
                # Keep in_table = True so parsing continues on the next page
                continue

            # Auto-start table if we encounter a perfect data line before a header
            if not in_table and _is_data_line(line):
                in_table = True
                flush_buffer_without_data()

            if not in_table:
                continue

            # ---- Skip blank / header-repeat lines inside the table ----
            if not line.strip():
                continue

            # Skip lines that are just the column header repeating
            if _TABLE_HEADER_RE.search(line):
                flush_buffer_without_data()
                continue

            # Skip the opening-balance line (record separately, not as a transaction)
            if _OPENING_BAL_RE.search(line):
                flush_buffer_without_data()
                continue

            # ---- Classify the line ----
            if _is_data_line(line):
                # This is PART B — resolve the transaction
                date_val, debit_val, credit_val, balance_val = _parse_data_line(
                    line, statement_year=statement_year
                )

                if date_val is None:
                    # Couldn't parse the date — treat as continuation description
                    desc_buffer.append(line.strip())
                    continue

                # Anything on the LEFT of the date column is description continuation
                left_part = line[:_COL_DATE_START].strip()
                if left_part and not re.match(r"^[\d,]+\.\d{2}$", left_part):
                    desc_buffer.append(left_part)

                commit_transaction(date_val, debit_val, credit_val, balance_val)

            else:
                # PART A — accumulate description text
                # Ignore lines that are purely numeric (stray OCR artefacts)
                stripped = line.strip()
                if re.match(r"^[\d\s,.$]+$", stripped):
                    continue
                desc_buffer.append(stripped)

        # Commit any trailing buffer (shouldn't happen in well-formed statements)
        flush_buffer_without_data()

        return transactions



register_parser(_BANK_ID, PalmettoStateBankParser)
register_template_parser(_TEMPLATE_ID, PalmettoStateBankParser)
