import logging
import re
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from fastapi import UploadFile
from app.core.config import UPLOAD_DIR
from app.models.schemas import StatementResult, Transaction
from app.parsers import ParserBuilder, ParserContext, ParserNotFoundError
from app.parsers.result import ParseResult
from app.services.altered_statement_detector import detect_altered_statement
from app.services.amount_utils import clean_amount
from app.services.date_utils import parse_date
from app.services.digital_extractor import (
    compile_digital_extraction_debug,
    extract_with_pdfplumber,
)
from app.services.file_service import write_file
from app.services.hash_service import (
    generate_content_hash,
    generate_file_hash,
)
from app.services.image_preprocessor import preprocess_scanned_pdf
from app.services.metadata_extractor import extract_statement_metadata
from app.services.ocr_extractor import extract_ocr_rows_with_debug
from app.services.pdf_type_detector import detect_pdf_type
from app.services.table_parser import (
    detect_balance_column_from_data,
    detect_header_row,
    map_columns,
    merge_wrapped_rows,
    normalize_header_row,
)
from app.services.postprocessor import (
    calculate_confidence,
    classify_debit_credit,
    classify_signed_amount,
    detect_statement_period,
    deduplicate_transactions,
    sum_transaction_totals,
)
from app.services.statement_templates import (
    lookup_template_by_bank_key,
    select_statement_template,
)

LOGGER = logging.getLogger(__name__)


def _add_reconciliation_warnings(
    transactions: List[Transaction],
    warnings: List[str],
) -> None:
    checks = 0
    failures = 0
    both_sides = 0

    for prev, curr in zip(transactions, transactions[1:]):
        if curr.debit is not None and curr.credit is not None:
            both_sides += 1
        if prev.balance is None or curr.balance is None:
            continue
        amount_delta = float(curr.credit or 0) - float(curr.debit or 0)
        expected = round(float(prev.balance) + amount_delta, 2)
        actual = round(float(curr.balance), 2)
        checks += 1
        if abs(expected - actual) > 0.05:
            failures += 1

    if both_sides:
        warnings.append(
            f"Validation warning: {both_sides} transaction(s) have both debit and credit values."
        )
    if checks >= 3 and failures / checks > 0.25:
        warnings.append(
            f"Validation warning: balance reconciliation failed for {failures}/{checks} adjacent rows."
        )


def _statement_result(
    *,
    filename: str,
    transactions: List[Transaction],
    confidence: float,
    pdf_type: Optional[str] = None,
    warnings: List[str],
    rows: List[List[str]],
    raw_text: str,
    header_idx: Optional[int] = None,
    file_hash: Optional[str] = None,
    content_hash: Optional[str] = None,
    is_duplicate: bool = False,
    duplicate_type: Optional[str] = None,
    duplicate_of: Optional[str] = None,
    duplicate_confidence: Optional[float] = None,
    duplicate_message: Optional[str] = None,
    is_altered: bool = False,
    alteration_risk_score: int = 0,
    alteration_risk_level: Optional[str] = None,
    alteration_reasons: Optional[List[str]] = None,
    alteration_signals: Optional[Dict] = None,
    rejected: bool = False,
    rejection_reason: Optional[str] = None,
    debug_extraction: Optional[Dict] = None,
) -> StatementResult:
    transactions = deduplicate_transactions(transactions)
    _add_reconciliation_warnings(transactions, warnings)
    totals = sum_transaction_totals(transactions)
    meta = extract_statement_metadata(rows, transactions, header_idx=header_idx)
    return StatementResult(
        filename=filename,
        transactions=transactions,
        confidence=confidence,
        pdf_type=pdf_type or "unknown",
        warnings=warnings,
        raw_text=raw_text,
        debug_extraction=debug_extraction or {},
        bank_name=meta["bank_name"],
        account_number=meta["account_number"],
        customer_name=meta["customer_name"],
        current_balance=meta["current_balance"],
        total_debits=totals["total_debits"],
        total_credits=totals["total_credits"],
        file_hash=file_hash,
        content_hash=content_hash,
        is_duplicate=is_duplicate,
        duplicate_type=duplicate_type,
        duplicate_of=duplicate_of,
        duplicate_confidence=duplicate_confidence,
        duplicate_message=duplicate_message,
        is_altered=is_altered,
        alteration_risk_score=alteration_risk_score,
        alteration_risk_level=alteration_risk_level,
        alteration_reasons=alteration_reasons or [],
        alteration_signals=alteration_signals or {},
        rejected=rejected,
        rejection_reason=rejection_reason,
    )


def _statement_result_from_parse_result(
    *,
    filename: str,
    parse_result: ParseResult,
    pdf_type: Optional[str],
    warnings: List[str],
    rows: List[List[str]],
    raw_text: str,
    header_idx: Optional[int] = None,
    debug_extraction: Optional[Dict] = None,
) -> StatementResult:
    transactions = deduplicate_transactions(parse_result.transactions)
    combined_warnings = [
        *warnings,
        *parse_result.warnings,
        *parse_result.validation_errors,
    ]
    _add_reconciliation_warnings(transactions, combined_warnings)
    totals = sum_transaction_totals(transactions)
    fallback_meta = extract_statement_metadata(
        rows,
        transactions,
        header_idx=header_idx,
    )
    metadata = parse_result.metadata
    bank_name = metadata.bank_name or fallback_meta["bank_name"]
    account_number = metadata.account_number or fallback_meta["account_number"]
    customer_name = (
        metadata.customer_name
        or metadata.account_holder
        or fallback_meta["customer_name"]
    )
    current_balance = (
        metadata.current_balance
        if metadata.current_balance is not None
        else metadata.closing_balance
    )
    if current_balance is None:
        current_balance = fallback_meta["current_balance"]

    return StatementResult(
        filename=filename,
        transactions=transactions,
        confidence=parse_result.confidence,
        pdf_type=pdf_type or "unknown",
        warnings=combined_warnings,
        raw_text=raw_text,
        debug_extraction=debug_extraction or {},
        bank_name=bank_name,
        account_number=account_number,
        customer_name=customer_name,
        current_balance=current_balance,
        total_debits=totals["total_debits"],
        total_credits=totals["total_credits"],
    )


def _split_date_from_cell(
    cell: str,
    *,
    statement_year: Optional[int] = None,
) -> Tuple[Optional[str], str]:
    cell = cell.strip()
    m = re.match(r'^(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b\s*(.*)', cell)
    if m:
        date_str = parse_date(m.group(1), statement_year=statement_year)
        if date_str:
            return date_str, m.group(2).strip()
    m = re.match(r'^(\d{4}-\d{1,2}-\d{1,2})\b\s*(.*)', cell)
    if m:
        date_str = parse_date(m.group(1), statement_year=statement_year)
        if date_str:
            return date_str, m.group(2).strip()
    return None, cell


def _parse_signed_amount_rows(
    rows: List[List[str]],
    col_map: Dict,
    header_idx: int,
    *,
    statement_year: Optional[int] = None,
) -> List[Transaction]:
    transactions: List[Transaction] = []
    data_rows = rows[header_idx + 1:]

    for row in data_rows:
        if not row or not any(str(c).strip() for c in row):
            continue

        date_str, leftover_desc = _split_date_from_cell(
            str(row[0]), statement_year=statement_year
        )
        if not date_str:
            row_text = ' '.join(str(c) for c in row).strip()
            if transactions and row_text:
                prev = transactions[-1]
                prev.description = f"{prev.description} {row_text}".strip()
            continue

        numeric_cells: List[Tuple[int, float]] = []
        for idx in range(len(row) - 1, -1, -1):
            val = clean_amount(str(row[idx]))
            if val is not None:
                numeric_cells.append((idx, val))
            if len(numeric_cells) >= 2:
                break

        if not numeric_cells:
            continue

        balance: Optional[float] = None
        amount_val: Optional[float] = None

        if len(numeric_cells) >= 2:
            balance = abs(numeric_cells[0][1])
            amount_val = numeric_cells[1][1]
            amount_idx = numeric_cells[1][0]
            balance_idx = numeric_cells[0][0]
        else:
            amount_val = numeric_cells[0][1]
            amount_idx = numeric_cells[0][0]
            balance_idx = -1

        desc_parts = []
        if leftover_desc:
            desc_parts.append(leftover_desc)
        for idx in range(1, len(row)):
            if idx == amount_idx or idx == balance_idx:
                continue
            cell_text = str(row[idx]).strip()
            if cell_text and clean_amount(cell_text) is None:
                desc_parts.append(cell_text)
        description = ' '.join(desc_parts).strip()

        if not description:
            description = ' '.join(str(c) for c in row).strip()

        row_text = ' '.join(str(c) for c in row)
        debit, credit = classify_signed_amount(str(amount_val), row_text)

        if debit is None and credit is None:
            continue

        transactions.append(Transaction(
            date=date_str,
            description=description,
            debit=debit,
            credit=credit,
            balance=balance,
        ))

    return transactions


def _parse_multicolumn_rows(
    rows: List[List[str]],
    col_map: Dict,
    header_idx: int,
    *,
    statement_year: Optional[int] = None,
) -> List[Transaction]:
    transactions: List[Transaction] = []
    data_rows = rows[header_idx + 1:]

    date_col = col_map.get('date')
    desc_col = col_map.get('description')
    amount_col = col_map.get('amount')
    balance_col = col_map.get('balance')
    tran_code_col = col_map.get('tran_code')

    for row in data_rows:
        if not row or not any(str(c).strip() for c in row):
            continue

        date_str: Optional[str] = None
        if date_col is not None and date_col < len(row):
            date_str = parse_date(str(row[date_col]), statement_year=statement_year)
        if not date_str:
            row_text = ' '.join(str(c) for c in row).strip()
            if transactions and row_text:
                prev = transactions[-1]
                prev.description = f"{prev.description} {row_text}".strip()
            continue

        desc_parts = []
        if tran_code_col is not None and tran_code_col < len(row):
            tc = str(row[tran_code_col]).strip()
            if tc and tc.lower() not in ('', 'none'):
                desc_parts.append(tc)
        if desc_col is not None and desc_col < len(row):
            d = str(row[desc_col]).strip()
            if d:
                desc_parts.append(d)
        description = ' '.join(desc_parts).strip()
        if not description:
            description = ' '.join(str(c) for c in row).strip()

        debit: Optional[float] = None
        credit: Optional[float] = None

        raw_amount = ""
        if amount_col is not None and amount_col < len(row):
            raw_amount = str(row[amount_col])
            if clean_amount(raw_amount) is None:
                numeric_cells = [
                    (idx, str(cell))
                    for idx, cell in enumerate(row)
                    if idx != balance_col and clean_amount(str(cell)) is not None
                ]
                if numeric_cells:
                    raw_amount = numeric_cells[-1][1]
        if raw_amount:
            row_text = ' '.join(str(c) for c in row)
            debit, credit = classify_signed_amount(raw_amount, row_text)
        else:
            debit, credit = classify_debit_credit(row, col_map)

        if debit is None and credit is None:
            continue

        balance: Optional[float] = None
        if balance_col is not None and balance_col < len(row):
            balance = clean_amount(str(row[balance_col]))
            if balance is not None:
                balance = abs(balance)

        transactions.append(Transaction(
            date=date_str,
            description=description,
            debit=debit,
            credit=credit,
            balance=balance,
        ))

    return transactions


def _detect_format(col_map: Dict, rows: List[List[str]], header_idx: int) -> str:
    has_amount = 'amount' in col_map
    has_debit = 'debit' in col_map
    has_credit = 'credit' in col_map
    has_check = 'check_number' in col_map
    has_tran_code = 'tran_code' in col_map

    if has_check or has_tran_code:
        return "multicolumn"

    if has_amount and not has_debit and not has_credit:
        header_cols = len(rows[header_idx]) if header_idx < len(rows) else 3
        data_rows = rows[header_idx + 1: header_idx + 20]
        wider_count = sum(1 for r in data_rows if len(r) > header_cols and r)
        if wider_count > len(data_rows) * 0.3:
            return "signed_amount"
        return "signed_amount"

    if has_debit and has_credit:
        return "standard"

    return "standard"


def _row_text(row: List[str]) -> str:
    return " ".join(str(c) for c in row if str(c).strip()).strip()


def _is_money_cell(value: str) -> bool:
    text = str(value).strip()
    return bool(
        re.search(r"\(?\$?\s*\d[\d,]*\.\d{2}-?\)?", text)
        or re.search(r"\(?\$?\s*\d{1,3}(?:,\d{3})+-?\)?", text)
    )


def _extract_money_values(value: str) -> List[float]:
    values: List[float] = []
    pattern = re.compile(r"[+-]?\(?\$?\s*\d[\d,]*\.\d{2}-?\)?")
    for match in pattern.finditer(str(value)):
        amount = clean_amount(match.group(0))
        if amount is not None:
            values.append(amount)
    return values


def _is_repeated_block_layout(rows: List[List[str]]) -> bool:
    text = "\n".join(_row_text(row).lower() for row in rows[:120])
    if "jpmorgan chase" in text or "chase.com" in text:
        return True
    header_hits = len(re.findall(r"\bdate\b.{0,30}\bdescription\b.{0,30}\bamount\b", text))
    return header_hits >= 2


def _is_sectioned_activity_layout(rows: List[List[str]]) -> bool:
    text = "\n".join(_row_text(row).lower() for row in rows[:120])
    return (
        "bank of america" in text
        or "business advantage" in text
        or (
            "deposits and other credits" in text
            and "withdrawals and other debits" in text
        )
    )


def _description_from_cells(
    cells: List[str],
    *,
    statement_year: Optional[int] = None,
) -> str:
    parts = []
    for cell in cells:
        value = str(cell).strip()
        if not value:
            continue
        if parse_date(value, statement_year=statement_year):
            continue
        if clean_amount(value) is not None:
            continue
        parts.append(value)
    return " ".join(parts).strip()


def _classify_amount_by_context(
    amount: float,
    text: str,
    section: Optional[str] = None,
) -> Tuple[Optional[float], Optional[float]]:
    upper = text.upper()
    if amount < 0:
        return abs(amount), None
    if section == "credit":
        return None, abs(amount)
    if section == "debit":
        return abs(amount), None
    compact = re.sub(r"\s+", "", upper)
    if "ATM" in upper or re.search(
        r"\b(WITHDRAWAL|DEBIT|CHECK|FEE|PAYMENT|PURCHASE|TRANSFER TO|PAID OUT|ACH DEBIT)\b",
        upper,
    ) or re.search(
        r"(WITHDRAWAL|DEBIT|PAYMENT|PURCHASE|CHECK)",
        compact,
    ):
        return abs(amount), None
    if re.search(
        r"\b(DEPOSIT|CREDIT|TRANSFER FROM|PAID IN|ACH CREDIT|INTEREST|REFUND)\b",
        upper,
    ):
        return None, abs(amount)
    return None, abs(amount)


def _parse_repeated_horizontal_blocks(
    rows: List[List[str]],
    *,
    statement_year: Optional[int] = None,
) -> List[Transaction]:
    """
    Parse layouts that repeat Date/Description/Amount blocks horizontally.
    Chase statements often use this compact multi-block table shape.
    """
    transactions: List[Transaction] = []

    for row in rows:
        if not row:
            continue
        normalized_header = " ".join(normalize_header_row(row)).lower()
        if "date" in normalized_header and "amount" in normalized_header:
            continue

        date_positions: List[Tuple[int, str]] = []
        for idx, cell in enumerate(row):
            date_value = parse_date(str(cell), statement_year=statement_year)
            if not date_value:
                date_value, _ = _split_date_from_cell(
                    str(cell), statement_year=statement_year
                )
            if date_value:
                date_positions.append((idx, date_value))

        if not date_positions:
            continue

        for pos_idx, (date_idx, date_value) in enumerate(date_positions):
            next_date_idx = (
                date_positions[pos_idx + 1][0]
                if pos_idx + 1 < len(date_positions)
                else len(row)
            )
            block = [str(c).strip() for c in row[date_idx:next_date_idx]]
            amount_candidates = [
                (idx, clean_amount(cell))
                for idx, cell in enumerate(block)
                if _is_money_cell(cell) and clean_amount(cell) is not None
            ]
            if not amount_candidates:
                continue
            amount_idx, amount = amount_candidates[-1]
            if amount is None:
                continue

            desc_cells = block[:amount_idx]
            date_from_first, leftover = _split_date_from_cell(
                desc_cells[0] if desc_cells else "", statement_year=statement_year
            )
            if date_from_first and leftover:
                desc_cells[0] = leftover
            description = _description_from_cells(
                desc_cells, statement_year=statement_year
            )
            if not description:
                description = _row_text(block)

            debit, credit = _classify_amount_by_context(amount, _row_text(block))
            transactions.append(Transaction(
                date=date_value,
                description=description,
                debit=debit,
                credit=credit,
                balance=None,
            ))

    return transactions


def _parse_sectioned_activity_rows(
    rows: List[List[str]],
    *,
    statement_year: Optional[int] = None,
) -> List[Transaction]:
    """
    Parse sectioned statements where table meaning comes from headings:
    Deposits/Credits are credits; Withdrawals/Checks/Fees are debits.
    """
    transactions: List[Transaction] = []
    section: Optional[str] = None

    for row in rows:
        row_text = _row_text(row)
        row_lower = row_text.lower()
        if not row_text:
            continue

        if re.search(r"\b(deposits?|credits?|additions?)\b", row_lower):
            section = "credit"
            if not re.search(r"\b\d{1,2}[/-]\d{1,2}\b", row_lower):
                continue
        elif re.search(r"\b(withdrawals?|debits?|checks?|fees?)\b", row_lower):
            section = "debit"
            if not re.search(r"\b\d{1,2}[/-]\d{1,2}\b", row_lower):
                continue
        elif re.search(r"\b(daily balance|summary|ending balance|service fees?)\b", row_lower):
            if "fee" not in row_lower:
                section = None
            continue

        date_value: Optional[str] = None
        date_cell_idx = 0
        leftover = ""
        for idx, cell in enumerate(row):
            date_value = parse_date(str(cell), statement_year=statement_year)
            if not date_value:
                date_value, leftover = _split_date_from_cell(
                    str(cell), statement_year=statement_year
                )
            if date_value:
                date_cell_idx = idx
                break
        if not date_value:
            continue

        amount_candidates = []
        for idx, cell in enumerate(row):
            amount = clean_amount(str(cell))
            if _is_money_cell(str(cell)) and amount is not None:
                amount_candidates.append((idx, amount))
        if not amount_candidates:
            continue

        amount_idx, amount = amount_candidates[-1]
        desc_cells = [str(c).strip() for c in row[date_cell_idx:amount_idx]]
        if desc_cells and leftover:
            desc_cells[0] = leftover
        description = _description_from_cells(desc_cells, statement_year=statement_year)
        if not description:
            description = row_text

        debit, credit = _classify_amount_by_context(amount, row_text, section)
        transactions.append(Transaction(
            date=date_value,
            description=description,
            debit=debit,
            credit=credit,
            balance=None,
        ))

    return transactions


# ── SoFi Bank: signed amount with TYPE column ─────────────────────────────

# Regex for single-cell SoFi rows (Jan/Feb format):
# "Jan 31, 2026 Debit Card ARCO #42551 AMPM -$40.35 $95,744.25 Transaction ID: 586-1"
# OR short-date variant:
# "04/01 Direct Deposit Payroll Hansen LLC +2,500.00 $106,486.15"
_SOFI_SINGLE_LINE_RE = re.compile(
    r"^"
    r"(?P<date>"
    r"(?:[A-Za-z]{3}\s+\d{1,2}(?:,?\s+\d{4})?)"  # "Jan 31, 2026" or "Jan 31"
    r"|(?:\d{1,2}/\d{1,2}(?:/\d{2,4})?)"           # "04/01" or "04/01/2026"
    r")\s+"
    r"(?P<type>Direct Deposit|Debit (?:Card|Purchase)|Bill Payment|Wire Transfer"
    r"|ACH Transfer|Interest (?:Credit|Earned)|Check Deposit|Deposit"
    r"|Direct Payment|Other)\s+"
    r"(?P<desc>.+?)\s+"
    r"(?P<amount>[+-]\$?[\d,]+\.?\d*)\s+"
    r"\$?(?P<balance>[\d,]+\.?\d*)"
    r"(?:\s+Transaction\s+ID:\s*\S+)?"
    r"\s*$",
    re.IGNORECASE,
)

_SOFI_TRANSACTION_ID_RE = re.compile(
    r"^\s*Transaction\s+ID:\s*\S+\s*$", re.IGNORECASE
)

_SOFI_SKIP_RE = re.compile(
    r"opening\s+balance|interest\s+accrues\s+daily|sofi\s+insured|"
    r"important\s+information|how\s+to\s+contact|deposit\s+agreement|"
    r"sofi\s+checking\s+and\s+savings|page\s+\d|"
    r"primary\s+account\s+holder|statement\s+period|member\s+since|"
    r"current\s+balance|beginning\s+balance|current\s+interest\s+rate|"
    r"annual\s+percentage|monthly\s+interest\s+(?:accrued|paid)|"
    r"ytd\s+interest\s+paid|"
    r"balances\s+below|transaction\s+details|"
    r"checking\s+account\s+-\s*\d|^\s*sofi\s*$|"
    r"w\.sofi\.com",
    re.IGNORECASE,
)


def _parse_sofi_amount_balance(
    raw: str,
) -> Tuple[Optional[float], Optional[float]]:
    """
    Split a SoFi amount+balance cell like "+2,500.00 $106,486.15" into
    (signed_amount, balance).  Also handles plain signed amounts.
    """
    raw = raw.strip()

    # Pattern: "+2,500.00 $106,486.15" or "-212.44 $108,073.71"
    m = re.match(
        r"([+-]\$?[\d,]+\.?\d*)\s+\$?([\d,]+\.?\d*)",
        raw,
    )
    if m:
        amount = clean_amount(m.group(1))
        balance = clean_amount(m.group(2))
        if balance is not None:
            balance = abs(balance)
        return amount, balance

    # Plain signed amount
    amount = clean_amount(raw)
    return amount, None


def _parse_sofi_signed_type_rows(
    rows: List[List[str]],
    *,
    statement_year: Optional[int] = None,
) -> List[Transaction]:
    """
    Parse SoFi Bank statements.

    SoFi layout rules:
      1. Single signed AMOUNT column: + for credits, − for debits
      2. Explicit TYPE column: "Direct Deposit", "Debit Purchase", etc.
      3. Transaction ID metadata lines must be skipped
      4. Date is MM/DD (year inferred) or "Mon DD, YYYY"
      5. No summary/total lines — totals computed from transactions
    """
    transactions: List[Transaction] = []
    in_transaction_table = False

    for row in rows:
        if not row or not any(str(c).strip() for c in row):
            continue

        row_text = " ".join(str(c) for c in row).strip()
        row_lower = row_text.lower()

        # Detect the SoFi header row to start parsing
        if "date" in row_lower and "type" in row_lower and "amount" in row_lower:
            in_transaction_table = True
            continue

        # Skip Transaction ID metadata lines
        if _SOFI_TRANSACTION_ID_RE.match(row_text):
            continue

        # Skip non-transaction content
        if _SOFI_SKIP_RE.search(row_text):
            # Re-enter transaction mode if we see a continued header
            if "date" in row_lower and "type" in row_lower and "amount" in row_lower:
                in_transaction_table = True
            continue

        if not in_transaction_table:
            continue

        # ─── Format A: Multi-cell rows ─────────────────────────────────
        # ["04/01", "Direct Deposit", "Payroll Hansen LLC", "+2,500.00 $106,486.15"]
        if len(row) >= 3:
            date_str = parse_date(str(row[0]).strip(), statement_year=statement_year)
            if date_str:
                txn_type = str(row[1]).strip() if len(row) > 1 else ""
                description = str(row[2]).strip() if len(row) > 2 else ""

                # Build description: TYPE + narration
                if txn_type and description:
                    full_desc = f"{txn_type} {description}"
                elif txn_type:
                    full_desc = txn_type
                else:
                    full_desc = description or row_text

                # Amount + balance: may be merged in one cell or separate
                amount_val: Optional[float] = None
                balance: Optional[float] = None

                if len(row) >= 5:
                    # Separate amount and balance cells
                    amount_val = clean_amount(str(row[3]))
                    balance = clean_amount(str(row[4]))
                    if balance is not None:
                        balance = abs(balance)
                elif len(row) >= 4:
                    # Merged amount+balance cell
                    amount_val, balance = _parse_sofi_amount_balance(str(row[3]))
                else:
                    # Try to find amount in remaining cells
                    for cell in row[2:]:
                        amount_val, balance = _parse_sofi_amount_balance(str(cell))
                        if amount_val is not None:
                            break

                if amount_val is not None:
                    if amount_val < 0:
                        debit = abs(amount_val)
                        credit = None
                    else:
                        debit = None
                        credit = abs(amount_val)

                    transactions.append(Transaction(
                        date=date_str,
                        description=full_desc,
                        debit=debit,
                        credit=credit,
                        balance=balance,
                    ))
                continue

        # ─── Format B: Single-cell rows ────────────────────────────────
        # "Jan 31, 2026 Debit Card ARCO #42551 AMPM -$40.35 $95,744.25 Transaction ID: 586-1"
        if len(row) == 1:
            line = str(row[0]).strip()

            # Strip trailing Transaction ID
            line_clean = re.sub(
                r"\s+Transaction\s+ID:\s*\S+\s*$", "", line, flags=re.IGNORECASE
            )

            m = _SOFI_SINGLE_LINE_RE.match(line)
            if m:
                date_str = parse_date(
                    m.group("date").strip(), statement_year=statement_year
                )
                if date_str:
                    txn_type = m.group("type").strip()
                    description = m.group("desc").strip()
                    full_desc = f"{txn_type} {description}"

                    amount_val = clean_amount(m.group("amount"))
                    balance_raw = m.group("balance")
                    balance = clean_amount(balance_raw)
                    if balance is not None:
                        balance = abs(balance)

                    if amount_val is not None:
                        if amount_val < 0:
                            debit = abs(amount_val)
                            credit = None
                        else:
                            debit = None
                            credit = abs(amount_val)

                        transactions.append(Transaction(
                            date=date_str,
                            description=full_desc,
                            debit=debit,
                            credit=credit,
                            balance=balance,
                        ))
                    continue

            # Fallback: try generic line-parsing for single-cell rows
            # that didn't match the strict regex but might still be data
            if not re.search(r"\d{1,2}[/\-]\d{1,2}", line_clean) and not re.search(
                r"[A-Za-z]{3}\s+\d{1,2}", line_clean
            ):
                continue

            # Extract date from start of line
            date_str = None
            leftover = line_clean
            # Try "Mon DD, YYYY" format first
            m_date = re.match(
                r"([A-Za-z]{3}\s+\d{1,2}(?:,?\s+\d{4})?)\s+(.*)", line_clean
            )
            if m_date:
                date_str = parse_date(
                    m_date.group(1).strip(), statement_year=statement_year
                )
                leftover = m_date.group(2).strip()
            if not date_str:
                m_date = re.match(
                    r"(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s+(.*)", line_clean
                )
                if m_date:
                    date_str = parse_date(
                        m_date.group(1).strip(), statement_year=statement_year
                    )
                    leftover = m_date.group(2).strip()

            if not date_str:
                continue

            # Extract amounts from the end of the leftover text
            amount_matches = list(re.finditer(
                r"[+-]?\$?[\d,]+\.\d{2}", leftover
            ))
            if not amount_matches:
                continue

            # Last match is typically balance, second-to-last is amount
            if len(amount_matches) >= 2:
                amount_val = clean_amount(amount_matches[-2].group())
                balance = clean_amount(amount_matches[-1].group())
                if balance is not None:
                    balance = abs(balance)
                desc_end = amount_matches[-2].start()
            else:
                amount_val = clean_amount(amount_matches[-1].group())
                balance = None
                desc_end = amount_matches[-1].start()

            description = leftover[:desc_end].strip()
            if not description:
                description = leftover

            if amount_val is not None:
                if amount_val < 0:
                    debit = abs(amount_val)
                    credit = None
                else:
                    debit = None
                    credit = abs(amount_val)

                transactions.append(Transaction(
                    date=date_str,
                    description=description,
                    debit=debit,
                    credit=credit,
                    balance=balance,
                ))

    return transactions

    return transactions


# ── Citibank: fragmented multi-line with split Debits/Credits/Balance ────

_CITI_CREDIT_TYPES = [
    "FUNDS TRANSFER", "ELECTRONIC CREDIT", "ATM DEPOSIT",
    "DEPOSIT", "RETURNED CHECK", "DEBIT CARD CREDI",
]

_CITI_DEBIT_TYPES = [
    "ACH DEBIT", "DEBIT CARD PURCH", "DEBIT CARD (POS)",
    "CBUSOL TRANSFER DEBIT", "SERVICE CHARGES", "SERVICE CHARGE",
    "OFF-US ATM WITHDRAWAL", "INCOMING WIRE TRAN FEE",
    "CHECK NO:", "NSF/OD/DAU CHARGE",
]

def _parse_citi_checking_rows(
    rows: List[List[str]],
    *,
    statement_year: Optional[int] = None,
) -> List[Transaction]:
    """
    Parse Citibank XLRM-style checking statements.
    
    Citibank layout rules:
      1. Cells are heavily fragmented by pdfplumber.
      2. Multi-line transactions with merchant/ref info on continuation rows.
      3. Card reference lines (8-char) must be skipped.
      4. Amounts are split into Debit/Credit columns but since cells are fragmented,
         we extract them from the end of the reconstructed row string and 
         classify direction based on the transaction TYPE in the description.
    """
    transactions: List[Transaction] = []
    current_txn: Optional[Transaction] = None
    in_transactions = False
    
    def flush():
        nonlocal current_txn
        if current_txn:
            desc = current_txn.description.strip()
            desc_upper = desc.upper()
            
            # Determine direction based on type prefix
            is_credit = False
            is_debit = False
            
            for t in _CITI_CREDIT_TYPES:
                # Compare without internal spaces since pdfplumber fragments words
                if desc_upper.replace(" ", "").startswith(t.replace(" ", "")):
                    is_credit = True
                    break
            
            if not is_credit:
                for t in _CITI_DEBIT_TYPES:
                    if desc_upper.replace(" ", "").startswith(t.replace(" ", "")):
                        is_debit = True
                        break
            
            # Fallback if prefix matching fails
            if not is_credit and not is_debit:
                if "DEPOSIT" in desc_upper or "CREDIT" in desc_upper:
                    is_credit = True
                else:
                    is_debit = True
                    
            if is_credit and current_txn.debit is not None:
                current_txn.credit = current_txn.debit
                current_txn.debit = None
                
            # Special parsing rules
            if current_txn.debit == 0.01 or current_txn.credit == 0.01:
                if "ACCTVERIFY" not in desc_upper:
                    desc += " [ACCTVERIFY]"
                    
            if "XLRM LLC" in desc_upper:
                desc += " [INTRA-ENTITY]"
                
            current_txn.description = desc
            transactions.append(current_txn)
            current_txn = None

    for row in rows:
        clean_cells = [str(c).strip() for c in row if str(c).strip()]
        if not clean_cells:
            continue
            
        row_text = " ".join(clean_cells)
        row_lower = row_text.lower()
        
        # Stop conditions
        if "total debits/credits" in row_lower or "customer service information" in row_lower:
            in_transactions = False
            break
            
        # Start conditions
        if "beginning bal" in row_lower or "date description" in row_lower or ("date" in row_lower and "debits" in row_lower and "credits" in row_lower) or ("checking activity" in row_lower and len(row_lower) < 20):
            # Sometimes "date description" is fragmented, "checking activity" works well
            in_transactions = True
            continue
            
        if not in_transactions:
            continue
            
        # Check for date match (MM/DD)
        date_match = re.match(r'^(0[1-9]|1[0-2])/([0-3][0-9])', row_text)
        if date_match:
            flush()
            month = int(date_match.group(1))
            day = int(date_match.group(2))
            
            year = statement_year or datetime.now().year
            try:
                dt = datetime(year, month, day)
                date_str = dt.strftime("%Y-%m-%d")
            except ValueError:
                date_str = f"{year}-{month:02d}-{day:02d}"
                
            # Extract amounts from the end
            # We use a pattern that allows spaces anywhere to handle fragmentation (e.g. "22 4.74", "104. 00")
            amounts_iter = list(re.finditer(r'(?:\d\s*){1,3}(?:,\s*(?:\d\s*){3})*\.\s*(?:\d\s*){2}', row_text))
            
            amt_val = None
            bal_val = None
            desc_end = len(row_text)
            
            if len(amounts_iter) >= 2:
                # Two amounts: Amount and Balance
                amt_val = clean_amount(re.sub(r'\s+', '', amounts_iter[-2].group()))
                bal_val = clean_amount(re.sub(r'\s+', '', amounts_iter[-1].group()))
                desc_end = amounts_iter[-2].start()
            elif len(amounts_iter) == 1:
                # One amount: Amount only (Balance missing/blank)
                amt_val = clean_amount(re.sub(r'\s+', '', amounts_iter[0].group()))
                desc_end = amounts_iter[0].start()
                
            desc = row_text[date_match.end():desc_end].strip()
            
            # Clean up fragmented known words
            desc = desc.replace("DEB IT", "DEBIT").replace("PURC H", "PURCH").replace("ELE CTRONIC", "ELECTRONIC").replace("CRED IT", "CREDIT")
            
            current_txn = Transaction(
                date=date_str,
                description=desc,
                debit=amt_val,
                credit=None,
                balance=bal_val,
            )
            
        elif current_txn:
            # Continuation line
            
            # Skip 8-character alphanumeric card ref codes that start the line
            # Often followed by fragmented card number "006 05 4" and Month "Mar 05"
            # Using a lenient regex to match the 8-char ref and anything that follows 
            # if it looks like card ref residue.
            if re.match(r'^[A-Z0-9]{8}(?:\s+0{2,3}\s*\d\s*\d\s*\d\s*\d)?', row_text):
                continue
                
            # Skip pure garbage fragment lines that just contain the end of card (e.g. "006054")
            if re.match(r'^0\s*0\s*\d\s*\d\s*\d\s*\d', row_text):
                continue
                
            # If the transaction is a CHECK NO:, we shouldn't append continuation lines
            if current_txn.description.upper().startswith("CHECK NO:"):
                continue
                
            current_txn.description += " " + row_text

    flush()
    return transactions


def process_single_statement(
    file_path: Path,
    *,
    bank_hint: Optional[str] = None,
) -> StatementResult:
    warnings: List[str] = []
    alteration = detect_altered_statement(file_path)
    if alteration.is_altered:
        LOGGER.warning(
            "[%s] rejected altered statement risk=%s score=%s reasons=%s",
            file_path.name,
            alteration.risk_level,
            alteration.risk_score,
            alteration.reasons,
        )
        return _statement_result(
            filename=file_path.name,
            transactions=[],
            confidence=0.0,
            pdf_type="rejected",
            warnings=[alteration.message, *alteration.reasons],
            rows=[],
            raw_text="",
            is_altered=True,
            alteration_risk_score=alteration.risk_score,
            alteration_risk_level=alteration.risk_level,
            alteration_reasons=alteration.reasons,
            alteration_signals=alteration.signals,
            rejected=True,
            rejection_reason=alteration.message,
        )
    if alteration.reasons:
        warnings.extend(f"Alteration screen: {reason}" for reason in alteration.reasons)

    suffix = file_path.suffix.lower()
    is_image = suffix in {'.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif'}

    if is_image:
        pdf_type = "scanned"
    else:
        pdf_type = detect_pdf_type(file_path)

    LOGGER.info(f"[{file_path.name}] type={pdf_type}")
    rows: List[List[str]] = []
    debug_extraction: Dict = {}

    if pdf_type == "digital":
        try:
            rows = extract_with_pdfplumber(file_path)
            debug_extraction = compile_digital_extraction_debug(file_path)
            LOGGER.info(f"[{file_path.name}] pdfplumber → {len(rows)} rows")
        except Exception as e:
            LOGGER.error(f"pdfplumber failed: {e}")
            warnings.append(f"Digital extraction failed, falling back to OCR: {e}")
            pdf_type = "scanned"

    if pdf_type == "scanned" or not rows:
        try:
            images = preprocess_scanned_pdf(file_path, dpi=200)
            debug_pages = []
            for page_number, img in enumerate(images, start=1):
                ocr_rows, debug_page = extract_ocr_rows_with_debug(
                    img,
                    page_number=page_number,
                )
                debug_pages.append(debug_page)
                if ocr_rows:
                    rows.extend(ocr_rows)
            debug_extraction = {
                "source": "paddleocr",
                "coordinate_system": "image_pixels_top_left",
                "pages": debug_pages,
                "page_count": len(debug_pages),
                "row_count": sum(len(page["rows"]) for page in debug_pages),
                "cell_count": sum(
                    len(row["cells"]) for page in debug_pages for row in page["rows"]
                ),
            }
            LOGGER.info(f"[{file_path.name}] OCR → {len(rows)} rows")
        except Exception as e:
            LOGGER.error(f"OCR failed: {e}")
            warnings.append(f"OCR extraction failed: {e}")

    if not rows:
        return _statement_result(
            filename=file_path.name,
            transactions=[],
            confidence=0.0,
            pdf_type=pdf_type,
            warnings=warnings + ["No data extracted from document"],
            rows=[],
            raw_text="",
        )

    stmt_year, stmt_month = detect_statement_period(rows)
    LOGGER.info(f"[{file_path.name}] statement_period year={stmt_year} month={stmt_month}")
    preliminary_meta = extract_statement_metadata(rows, [], header_idx=None)

    # ── Template selection: manual hint vs auto-detect ──────────────────
    if bank_hint and bank_hint not in ("all", "auto"):
        template = lookup_template_by_bank_key(
            bank_hint, rows, filename=file_path.name,
        )
        if template:
            LOGGER.info(
                "[%s] bank_hint=%s → template=%s parser=%s",
                file_path.name,
                bank_hint,
                template.template_id,
                template.parser_format,
            )
        else:
            warnings.append(
                f"Bank hint '{bank_hint}' has no template — falling back to auto-detect"
            )
            template = select_statement_template(
                rows,
                filename=file_path.name,
                bank_name=preliminary_meta.get("bank_name"),
            )
    else:
        template = select_statement_template(
            rows,
            filename=file_path.name,
            bank_name=preliminary_meta.get("bank_name"),
        )
    if template:
        LOGGER.info(
            "[%s] template=%s layout=%s parser=%s",
            file_path.name,
            template.template_id,
            template.layout_family,
            template.parser_format,
        )

    raw_text_preview = "\n".join(" | ".join(str(c) for c in r) for r in rows[:20])
    context_bank_id = None
    if bank_hint and bank_hint not in ("all", "auto"):
        context_bank_id = bank_hint
    elif template:
        context_bank_id = template.bank_name
    else:
        context_bank_id = preliminary_meta.get("bank_name")

    parser_context = ParserContext(
        rows=rows,
        pdf_type=pdf_type,
        filename=file_path.name,
        bank_id=context_bank_id,
        bank_hint=bank_hint,
        template_id=template.template_id if template else None,
        parser_format=template.parser_format if template else None,
        statement_year=stmt_year,
        statement_month=stmt_month,
        debug_extraction=debug_extraction,
    )
    try:
        parser = ParserBuilder.get_parser(
            context_bank_id,
            parser_context,
            template_id=parser_context.template_id,
            parser_format=parser_context.parser_format,
        )
        parse_result = parser.parse()
        if parse_result.transactions:
            LOGGER.info(
                "[%s] builder parser=%s bank=%s template=%s -> %d transactions",
                file_path.name,
                parse_result.parser_id,
                parse_result.bank_id,
                parse_result.template_id,
                len(parse_result.transactions),
            )
            return _statement_result_from_parse_result(
                filename=file_path.name,
                parse_result=parse_result,
                pdf_type=pdf_type,
                warnings=warnings,
                rows=rows,
                raw_text=raw_text_preview,
                header_idx=detect_header_row(rows),
                debug_extraction=debug_extraction,
            )
        warnings.append(
            f"Builder parser '{parser.parser_id}' returned no transactions; falling back"
        )
    except ParserNotFoundError:
        LOGGER.info("[%s] no registered builder parser; using legacy flow", file_path.name)
    except Exception as exc:
        LOGGER.warning(
            "[%s] builder parser failed; using legacy flow: %s",
            file_path.name,
            exc,
            exc_info=True,
        )
        warnings.append(f"Builder parser failed; falling back to legacy flow: {exc}")

    # Citibank: fragmented multi-line
    citi_transactions: List[Transaction] = []
    if template and template.parser_format == "citi_checking":
        citi_transactions = _parse_citi_checking_rows(
            rows, statement_year=stmt_year
        )
    if citi_transactions:
        confidence = calculate_confidence([t.dict() for t in citi_transactions])
        raw_text = "\n".join(" | ".join(str(c) for c in r) for r in rows[:20])
        LOGGER.info(
            "[%s] citi_checking -> %d transactions",
            file_path.name,
            len(citi_transactions),
        )
        return _statement_result(
            filename=file_path.name,
            transactions=citi_transactions,
            confidence=confidence,
            pdf_type=pdf_type,
            warnings=warnings,
            rows=rows,
            raw_text=raw_text,
            header_idx=detect_header_row(rows),
        )

    # SoFi Bank: signed amount with TYPE column
    sofi_transactions: List[Transaction] = []
    if template and template.parser_format == "sofi_signed_type":
        sofi_transactions = _parse_sofi_signed_type_rows(
            rows, statement_year=stmt_year
        )
    if sofi_transactions:
        confidence = calculate_confidence([t.dict() for t in sofi_transactions])
        raw_text = "\n".join(" | ".join(str(c) for c in r) for r in rows[:20])
        LOGGER.info(
            "[%s] sofi_signed_type -> %d transactions",
            file_path.name,
            len(sofi_transactions),
        )
        return _statement_result(
            filename=file_path.name,
            transactions=sofi_transactions,
            confidence=confidence,
            pdf_type=pdf_type,
            warnings=warnings,
            rows=rows,
            raw_text=raw_text,
            header_idx=detect_header_row(rows),
        )

    repeated_transactions: List[Transaction] = []
    if (template and template.parser_format == "repeated_blocks") or (
        template is None and _is_repeated_block_layout(rows)
    ):
        repeated_transactions = _parse_repeated_horizontal_blocks(
            rows, statement_year=stmt_year
        )
    if repeated_transactions:
        confidence = calculate_confidence([t.dict() for t in repeated_transactions])
        raw_text = "\n".join(" | ".join(str(c) for c in r) for r in rows[:20])
        LOGGER.info(
            "[%s] repeated_blocks -> %d transactions",
            file_path.name,
            len(repeated_transactions),
        )
        return _statement_result(
            filename=file_path.name,
            transactions=repeated_transactions,
            confidence=confidence,
            pdf_type=pdf_type,
            warnings=warnings,
            rows=rows,
            raw_text=raw_text,
            header_idx=detect_header_row(rows),
        )

    sectioned_transactions: List[Transaction] = []
    if (template and template.parser_format == "sectioned") or (
        template is None and _is_sectioned_activity_layout(rows)
    ):
        sectioned_transactions = _parse_sectioned_activity_rows(
            rows, statement_year=stmt_year
        )
    if sectioned_transactions:
        confidence = calculate_confidence([t.dict() for t in sectioned_transactions])
        raw_text = "\n".join(" | ".join(str(c) for c in r) for r in rows[:20])
        LOGGER.info(
            "[%s] sectioned -> %d transactions",
            file_path.name,
            len(sectioned_transactions),
        )
        return _statement_result(
            filename=file_path.name,
            transactions=sectioned_transactions,
            confidence=confidence,
            pdf_type=pdf_type,
            warnings=warnings,
            rows=rows,
            raw_text=raw_text,
            header_idx=detect_header_row(rows),
        )

    add_sub_transactions: List[Transaction] = []
    if template is None or template.parser_format == "additions_subtractions":
        add_sub_transactions = _parse_additions_subtractions_rows(
            rows, statement_year=stmt_year
        )
    if add_sub_transactions:
        confidence = calculate_confidence([t.dict() for t in add_sub_transactions])
        raw_text = "\n".join(" | ".join(str(c) for c in r) for r in rows[:20])
        return _statement_result(
            filename=file_path.name,
            transactions=add_sub_transactions,
            confidence=confidence,
            pdf_type=pdf_type,
            warnings=warnings,
            rows=rows,
            raw_text=raw_text,
            header_idx=detect_header_row(rows),
        )

    header_idx = detect_header_row(rows)
    if header_idx is None:
        warnings.append("Header row not detected – using row 0")
        header_idx = 0

    header_row = rows[header_idx]
    LOGGER.info(f"[{file_path.name}] header={header_row}")

    col_map = map_columns(header_row)
    LOGGER.info(f"[{file_path.name}] col_map={col_map}")

    if not col_map:
        warnings.append("Column mapping failed – attempting line-by-line parse")
        data_rows = rows[header_idx + 1:]
        transactions = _parse_lines_heuristic(
            data_rows, file_path.name, statement_year=stmt_year
        )
        transactions.extend(_parse_check_detail_rows(rows, statement_year=stmt_year))
        confidence = calculate_confidence([t.dict() for t in transactions])
        raw_text = "\n".join(" | ".join(str(c) for c in r) for r in rows[:20])
        LOGGER.info(f"[{file_path.name}] heuristic → {len(transactions)} transactions")
        return _statement_result(
            filename=file_path.name,
            transactions=transactions,
            confidence=confidence,
            pdf_type=pdf_type,
            warnings=warnings,
            rows=rows,
            raw_text=raw_text,
            header_idx=header_idx,
        )

    fmt = (
        template.parser_format
        if template and template.parser_format in {"signed_amount", "multicolumn", "standard"}
        else _detect_format(col_map, rows, header_idx)
    )
    LOGGER.info(f"[{file_path.name}] format={fmt}")

    if fmt == "signed_amount":
        transactions = _parse_signed_amount_rows(
            rows, col_map, header_idx, statement_year=stmt_year
        )
        transactions.extend(_parse_check_detail_rows(rows, statement_year=stmt_year))
        confidence = calculate_confidence([t.dict() for t in transactions])
        raw_text = "\n".join(" | ".join(str(c) for c in r) for r in rows[:20])
        LOGGER.info(f"[{file_path.name}] signed_amount → {len(transactions)} transactions")
        return _statement_result(
            filename=file_path.name,
            transactions=transactions,
            confidence=confidence,
            pdf_type=pdf_type,
            warnings=warnings,
            rows=rows,
            raw_text=raw_text,
            header_idx=header_idx,
        )

    if fmt == "multicolumn":
        transactions = _parse_multicolumn_rows(
            rows, col_map, header_idx, statement_year=stmt_year
        )
        transactions.extend(_parse_check_detail_rows(rows, statement_year=stmt_year))
        confidence = calculate_confidence([t.dict() for t in transactions])
        raw_text = "\n".join(" | ".join(str(c) for c in r) for r in rows[:20])
        LOGGER.info(f"[{file_path.name}] multicolumn → {len(transactions)} transactions")
        return _statement_result(
            filename=file_path.name,
            transactions=transactions,
            confidence=confidence,
            pdf_type=pdf_type,
            warnings=warnings,
            rows=rows,
            raw_text=raw_text,
            header_idx=header_idx,
        )

    data_rows = rows[header_idx + 1:]
    date_col = col_map.get('date')
    if date_col is not None:
        data_rows = merge_wrapped_rows(data_rows, date_col)

    balance_col = detect_balance_column_from_data(data_rows, col_map)
    if balance_col is not None and 'balance' not in col_map:
        col_map['balance'] = balance_col

    transactions: List[Transaction] = []
    rows_processed = rows_with_dates = 0

    for row in data_rows:
        if not row or not any(str(c).strip() for c in row):
            continue
        rows_processed += 1

        date_str: Optional[str] = None
        if date_col is not None and date_col < len(row):
            date_str = parse_date(str(row[date_col]), statement_year=stmt_year)
        if date_str:
            rows_with_dates += 1
        else:
            continue

        desc = ""
        if 'description' in col_map and col_map['description'] < len(row):
            desc = str(row[col_map['description']]).strip()
        if not desc:
            desc = " ".join(str(c) for c in row).strip()

        debit, credit = classify_debit_credit(
            row, col_map, balance_col=col_map.get('balance')
        )

        compact_balance: Optional[float] = None
        if debit is None and credit is None and 'amount' in col_map:
            amount_idx = col_map['amount']
            if amount_idx < len(row):
                money_values = _extract_money_values(str(row[amount_idx]))
                if money_values:
                    debit, credit = _classify_amount_by_context(
                        money_values[0], " ".join(str(c) for c in row)
                    )
                    if len(money_values) > 1:
                        compact_balance = abs(money_values[1])

        if debit is None and credit is None:
            continue

        balance: Optional[float] = None
        if compact_balance is not None:
            balance = compact_balance
        if 'balance' in col_map and col_map['balance'] < len(row):
            balance = clean_amount(str(row[col_map['balance']]))
            if balance is not None:
                balance = abs(balance)

        transactions.append(Transaction(
            date=date_str,
            description=desc,
            debit=debit,
            credit=credit,
            balance=balance,
        ))

    transactions.extend(_parse_check_detail_rows(rows, statement_year=stmt_year))
    confidence = calculate_confidence([t.dict() for t in transactions])
    LOGGER.info(
        f"[{file_path.name}] rows={len(rows)} data={len(data_rows)} "
        f"processed={rows_processed} dated={rows_with_dates} "
        f"transactions={len(transactions)} confidence={confidence}"
    )

    if not transactions and rows_with_dates == 0:
        warnings.append(f"No dates recognised in {rows_processed} rows")

    raw_text = "\n".join(" | ".join(str(c) for c in r) for r in rows[:20])
    return _statement_result(
        filename=file_path.name,
        transactions=transactions,
        confidence=confidence,
        pdf_type=pdf_type,
        warnings=warnings,
        rows=rows,
        raw_text=raw_text,
        header_idx=header_idx,
    )


def _parse_lines_heuristic(
    rows: List[List[str]],
    filename: str,
    *,
    statement_year: Optional[int] = None,
) -> List[Transaction]:
    transactions: List[Transaction] = []

    for row in rows:
        if not row:
            continue

        full_line = " ".join(str(c) for c in row)
        date_str: Optional[str] = None
        for cell in row:
            date_str = parse_date(str(cell), statement_year=statement_year)
            if date_str:
                break
        if not date_str:
            date_str, _ = _split_date_from_cell(
                str(row[0]), statement_year=statement_year
            )
        if not date_str:
            continue

        desc_candidates = []
        for cell in row:
            s = str(cell).strip()
            if not s:
                continue
            if parse_date(s, statement_year=statement_year):
                continue
            if clean_amount(s) is not None:
                continue
            desc_candidates.append(s)
        description = " ".join(desc_candidates).strip() or full_line

        amounts = []
        for cell in row:
            v = clean_amount(str(cell))
            if v is not None:
                amounts.append(v)

        debit: Optional[float] = None
        credit: Optional[float] = None
        balance: Optional[float] = None

        if len(amounts) >= 3:
            balance = abs(amounts[-1])
            for v in amounts[:-1]:
                if v < 0:
                    debit = abs(v)
                elif v > 0:
                    credit = v
        elif len(amounts) == 2:
            balance = abs(amounts[-1])
            v = amounts[0]
            row_up = full_line.upper()
            if re.search(
                r'\b(WITHDRAWAL|DEBIT|PURCHASE|CHARGE|FEE|PAYMENT|TRANSFER\s*TO|POS\s*DEB|CHECK)\b',
                row_up,
            ):
                debit = abs(v)
            else:
                credit = v
        elif len(amounts) == 1:
            v = amounts[0]
            row_up = full_line.upper()
            if v < 0 or re.search(
                r'\b(WITHDRAWAL|DEBIT|PURCHASE|CHARGE|FEE|PAYMENT|TRANSFER\s*TO|POS\s*DEB|CHECK)\b',
                row_up,
            ):
                debit = abs(v)
            else:
                credit = abs(v)

        transactions.append(Transaction(
            date=date_str,
            description=description,
            debit=debit,
            credit=credit,
            balance=balance,
        ))

    return transactions


def _parse_additions_subtractions_rows(
    rows: List[List[str]],
    *,
    statement_year: Optional[int] = None,
) -> List[Transaction]:
    transactions: List[Transaction] = []
    in_activity_table = False

    for row in rows:
        row_text = " ".join(str(c) for c in row).strip()
        row_lower = row_text.lower()

        has_add_sub_header = (
            "date" in row_lower
            and "description" in row_lower
            and ("additions" in row_lower or "subtractions" in row_lower)
        )
        if has_add_sub_header:
            in_activity_table = True
            continue

        if in_activity_table and (
            "daily balance" in row_lower
            or "checks in number" in row_lower
            or "deposits and other" in row_lower
        ):
            in_activity_table = False

        if not in_activity_table or not row:
            continue

        date_str = parse_date(str(row[0]), statement_year=statement_year)
        if not date_str:
            if transactions and row_text:
                previous = transactions[-1]
                previous.description = f"{previous.description} {row_text}".strip()
            continue

        description = str(row[1]).strip() if len(row) > 1 else row_text
        credit = clean_amount(str(row[2])) if len(row) > 2 else None
        debit = clean_amount(str(row[3])) if len(row) > 3 else None

        if credit is not None and credit < 0:
            debit = abs(credit)
            credit = None
        if debit is not None:
            debit = abs(debit)
        if credit is not None:
            credit = abs(credit)

        if debit is None and credit is None:
            continue

        transactions.append(Transaction(
            date=date_str,
            description=description or row_text,
            debit=debit,
            credit=credit,
            balance=None,
        ))

    return transactions


def _parse_check_detail_rows(
    rows: List[List[str]],
    *,
    statement_year: Optional[int] = None,
) -> List[Transaction]:
    transactions: List[Transaction] = []
    seen = set()

    pattern = re.compile(
        r"Number:\s*([A-Za-z0-9-]+)\s+Date:\s*([0-9/.\-]+)\s+Amount:\s*\$?\s*([0-9,]+\.\d{2})",
        re.IGNORECASE,
    )

    for row in rows:
        row_text = " ".join(str(c) for c in row)
        for match in pattern.finditer(row_text):
            check_number, raw_date, raw_amount = match.groups()
            date_str = parse_date(raw_date, statement_year=statement_year)
            amount = clean_amount(raw_amount)
            if not date_str or amount is None:
                continue

            key = (check_number, date_str, round(abs(amount), 2))
            if key in seen:
                continue
            seen.add(key)

            description = f"Check {check_number}"
            transactions.append(Transaction(
                date=date_str,
                description=description,
                debit=abs(amount),
                credit=None,
                balance=None,
            ))

    return transactions


async def process_uploaded_file(
    upload: UploadFile,
    *,
    with_duplicate_check: bool,
    bank_hint: Optional[str] = None,
) -> StatementResult:
    original_filename = upload.filename or f"document-{uuid.uuid4().hex}.bin"
    target_path = UPLOAD_DIR / f"{uuid.uuid4().hex}_{original_filename}"

    try:
        await write_file(upload, target_path)

        file_hash = None
        content_hash = None

        if with_duplicate_check:
            file_hash = generate_file_hash(target_path)
            LOGGER.info(f"File hash for {original_filename}: {file_hash[:16]}...")

        result = process_single_statement(target_path, bank_hint=bank_hint)
        result.filename = original_filename

        if with_duplicate_check:
            metadata = {
                "bank_name": result.bank_name,
                "account_number": result.account_number,
                "current_balance": result.current_balance,
            }
            content_hash = generate_content_hash(result.transactions, metadata)
            result.file_hash = file_hash
            result.content_hash = content_hash

        LOGGER.info(
            f"Done: {original_filename} → "
            f"{len(result.transactions)} transactions, "
            f"confidence={result.confidence}"
        )
        return result
    except Exception as exc:
        LOGGER.error(f"Failed: {original_filename}: {exc}", exc_info=True)
        return StatementResult(
            filename=original_filename,
            transactions=[],
            confidence=0.0,
            pdf_type="unknown",
            warnings=[f"Processing failed: {exc}"],
            raw_text="",
        )
    finally:
        try:
            if target_path.exists():
                target_path.unlink()
        except Exception:
            pass
