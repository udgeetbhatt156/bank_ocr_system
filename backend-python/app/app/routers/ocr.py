"""
OCR Router - Main processing pipeline
Handles digital PDFs, scanned PDFs, and image files.
Supports PeoplesSouth, BancFirst, BMO, Suncoast, US Bank, HDFC, ICICI,
YES Bank, Bank of Baroda, etc.
"""
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging
import re

import aiofiles
import pdfplumber
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import UPLOAD_DIR
from app.models.schemas import OCRResponse, StatementResult, Transaction
from app.services.ingestion import detect_pdf_type
from app.services.preprocessor import preprocess_scanned_pdf
from app.services.ocr_engine import (
    extract_digital_pdf,
    extract_ocr_rows,
    run_paddleocr_structure,
    parse_ocr_text_to_rows,
)
from app.services.table_parser import (
    map_columns,
    merge_wrapped_rows,
    detect_header_row,
    detect_balance_column_from_data,
)
from app.services.postprocessor import (
    clean_amount,
    parse_date,
    classify_debit_credit,
    classify_signed_amount,
    calculate_confidence,
    detect_statement_period,
)
from app.services.metadata_extractor import extract_statement_metadata
from app.services.revenue_filter import apply_revenue_filter
from app.services.duplicate_detector import check_for_duplicates
from app.services.hash_service import (
    generate_file_hash,
    generate_content_hash,
    generate_transaction_fingerprint,
)

router = APIRouter()
LOGGER = logging.getLogger(__name__)


def _statement_result(
    *,
    filename: str,
    transactions: List[Transaction],
    confidence: float,
    pdf_type: str,
    warnings: List[str],
    rows: List[List[str]],
    raw_text: str,
    header_idx: Optional[int] = None,
    file_hash: Optional[str] = None,
    content_hash: Optional[str] = None,
    fingerprint: Optional[str] = None,
    is_duplicate: bool = False,
    duplicate_type: Optional[str] = None,
    duplicate_of: Optional[str] = None,
    duplicate_confidence: Optional[float] = None,
    duplicate_message: Optional[str] = None,
) -> StatementResult:
    revenue_snapshot = apply_revenue_filter(transactions)
    meta = extract_statement_metadata(rows, transactions, header_idx=header_idx)
    return StatementResult(
        filename=filename,
        transactions=transactions,
        confidence=confidence,
        pdf_type=pdf_type,
        warnings=warnings,
        raw_text=raw_text,
        bank_name=meta["bank_name"],
        account_number=meta["account_number"],
        customer_number=meta["customer_number"],
        current_balance=meta["current_balance"],
        raw_credits=revenue_snapshot["raw_credits"],
        adjusted_revenue=revenue_snapshot["adjusted_revenue"],
        revenue_deductions=revenue_snapshot["revenue_deductions"],
        total_debits=revenue_snapshot["total_debits"],
        file_hash=file_hash,
        content_hash=content_hash,
        fingerprint=fingerprint,
        is_duplicate=is_duplicate,
        duplicate_type=duplicate_type,
        duplicate_of=duplicate_of,
        duplicate_confidence=duplicate_confidence,
        duplicate_message=duplicate_message,
    )


# File writer

async def write_file(upload_file: UploadFile, destination: Path) -> Path:
    async with aiofiles.open(destination, "wb") as f:
        while chunk := await upload_file.read(65536):
            await f.write(chunk)
    return destination


# Smart pdfplumber extraction

def extract_with_pdfplumber(file_path: Path) -> List[List[str]]:
    """
    Try table extraction first; fall back to word-level line reconstruction.
    This handles BMO-style PDFs where pdfplumber finds no tables but the text
    is laid out in columns.
    """
    all_rows: List[List[str]] = []

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_width = page.width or 612  # default letter width

            # ── Try structured table extraction first ──
            # Use text-based strategies for statements without visible gridlines
            tables = page.extract_tables()
            if not tables:
                tables = page.extract_tables({
                    "vertical_strategy": "text",
                    "horizontal_strategy": "text",
                    "min_words_vertical": 3,
                    "min_words_horizontal": 1,
                })
            if tables:
                for table in tables:
                    for row in table:
                        cleaned = [str(c).strip() if c else "" for c in row]
                        if any(cleaned):
                            all_rows.append(cleaned)
                continue  # page handled

            # ── Fall back: reconstruct rows from word positions ──
            words = page.extract_words(
                x_tolerance=5,
                y_tolerance=5,
                keep_blank_chars=False,
                use_text_flow=False,
            )
            if not words:
                # Last resort: plain text split by newline
                text = page.extract_text() or ""
                for line in text.splitlines():
                    parts = [p.strip() for p in re.split(r'\s{2,}', line) if p.strip()]
                    if parts:
                        all_rows.append(parts)
                continue

            # Group words into lines by their top-y coordinate.
            # Use median word height for dynamic tolerance instead of a
            # hardcoded 3px grid.
            heights = [w.get('height', w['bottom'] - w['top']) for w in words]
            median_h = sorted(heights)[len(heights) // 2] if heights else 12
            y_tol = max(4, median_h * 0.5)

            lines: dict = {}
            for w in words:
                y_key = round(w['top'] / y_tol) * y_tol
                lines.setdefault(y_key, []).append(w)

            # Dynamic column gap threshold based on page width.
            # Bank statements typically have column gaps of 15-40px on a
            # 612px wide page.
            col_gap = max(12, page_width * 0.02)

            for y_key in sorted(lines):
                line_words = sorted(lines[y_key], key=lambda w: w['x0'])
                # Cluster words into columns by x-gap
                cols: List[str] = []
                current = line_words[0]['text']
                for prev, curr in zip(line_words, line_words[1:]):
                    gap = curr['x0'] - prev['x1']
                    if gap > col_gap:  # column separator
                        cols.append(current.strip())
                        current = curr['text']
                    else:
                        current += ' ' + curr['text']
                cols.append(current.strip())
                if any(cols):
                    all_rows.append(cols)

    return all_rows


# Date+description split 

def _split_date_from_cell(
    cell: str,
    *,
    statement_year: Optional[int] = None,
) -> Tuple[Optional[str], str]:
    """
    If *cell* starts with a date (e.g. "1/02 BILLNG MERCH BANKCARD"),
    return (parsed_date, remaining_text).  Otherwise return (None, cell).
    """
    cell = cell.strip()
    # Try matching "MM/DD" or "MM/DD/YYYY" at the start of the cell
    m = re.match(r'^(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b\s*(.*)', cell)
    if m:
        date_str = parse_date(m.group(1), statement_year=statement_year)
        if date_str:
            remainder = m.group(2).strip()
            return date_str, remainder

    # Also try "YYYY-MM-DD" at the start
    m = re.match(r'^(\d{4}-\d{1,2}-\d{1,2})\b\s*(.*)', cell)
    if m:
        date_str = parse_date(m.group(1), statement_year=statement_year)
        if date_str:
            return date_str, m.group(2).strip()

    return None, cell


# Signed-amount format parser (PeoplesSouth / Sneads)

def _parse_signed_amount_rows(
    rows: List[List[str]],
    col_map: Dict,
    header_idx: int,
    *,
    statement_year: Optional[int] = None,
) -> List[Transaction]:
    """
    Parse transactions from a 'Date | Description | Amount' format where:
      - Amounts are signed: negative (trailing '-') = debit, positive = credit
      - The running balance is an extra trailing column not in the header
      - The date may be merged with the first part of the description in cell 0

    This handles PeoplesSouth / Sneads Tire bank statements and similar formats.
    """
    transactions: List[Transaction] = []
    data_rows = rows[header_idx + 1:]

    for row in data_rows:
        if not row or not any(str(c).strip() for c in row):
            continue

        # ── Find the date ──
        # The date is usually at the start of cell 0, possibly merged with
        # description text (e.g. "1/02 BILLNG MERCH BANKCARD")
        date_str, leftover_desc = _split_date_from_cell(
            str(row[0]), statement_year=statement_year
        )
        if not date_str:
            # Not a transaction row – might be a continuation.
            # Append text to previous transaction's description.
            row_text = ' '.join(str(c) for c in row).strip()
            if transactions and row_text:
                prev = transactions[-1]
                prev.description = f"{prev.description} {row_text}".strip()
                prev.source_line = f"{prev.source_line} | {row_text}"
            continue

        # ── Identify amount and balance from the right side ──
        # Scan cells from right-to-left; the rightmost numeric value is the
        # running balance, the next numeric value is the signed transaction
        # amount.
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
            # Last = balance, second-to-last = amount
            balance = abs(numeric_cells[0][1])
            amount_val = numeric_cells[1][1]
            amount_idx = numeric_cells[1][0]
            balance_idx = numeric_cells[0][0]
        else:
            # Only one numeric cell – treat as the amount
            amount_val = numeric_cells[0][1]
            amount_idx = numeric_cells[0][0]
            balance_idx = -1

        # ── Build description from non-date, non-amount cells ──
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

        # ── Classify debit/credit from signed amount ──
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
            reference=None,
            source_line=" | ".join(str(c) for c in row),
        ))

    return transactions


# Multi-column format parser (04-2026 MTD style) 

def _parse_multicolumn_rows(
    rows: List[List[str]],
    col_map: Dict,
    header_idx: int,
    *,
    statement_year: Optional[int] = None,
) -> List[Transaction]:
    """
    Parse transactions from a multi-column format like:
      Date | Check# | TranCode | Description | Amount | Balance

    Where Amount uses parentheses for debits: ($234.18) = debit, $1500 = credit.
    The check number is used as a reference.
    """
    transactions: List[Transaction] = []
    data_rows = rows[header_idx + 1:]

    # Determine column indices
    date_col = col_map.get('date')
    desc_col = col_map.get('description')
    amount_col = col_map.get('amount')
    balance_col = col_map.get('balance')
    check_col = col_map.get('check_number') or col_map.get('reference')
    tran_code_col = col_map.get('tran_code')

    for row in data_rows:
        if not row or not any(str(c).strip() for c in row):
            continue

        # ── Date ──
        date_str: Optional[str] = None
        if date_col is not None and date_col < len(row):
            date_str = parse_date(str(row[date_col]), statement_year=statement_year)
        if not date_str:
            # Continuation row – merge description
            row_text = ' '.join(str(c) for c in row).strip()
            if transactions and row_text:
                prev = transactions[-1]
                prev.description = f"{prev.description} {row_text}".strip()
                prev.source_line = f"{prev.source_line} | {row_text}"
            continue

        # ── Description ──
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

        # ── Amount (signed) ──
        debit: Optional[float] = None
        credit: Optional[float] = None

        if amount_col is not None and amount_col < len(row):
            raw_amount = str(row[amount_col])
            row_text = ' '.join(str(c) for c in row)
            debit, credit = classify_signed_amount(raw_amount, row_text)
        else:
            # Fallback: try separate debit/credit columns
            debit, credit = classify_debit_credit(row, col_map)

        if debit is None and credit is None:
            continue

        # ── Balance ──
        balance: Optional[float] = None
        if balance_col is not None and balance_col < len(row):
            balance = clean_amount(str(row[balance_col]))
            if balance is not None:
                balance = abs(balance)

        # ── Reference ──
        reference: Optional[str] = None
        if check_col is not None and check_col < len(row):
            ref = str(row[check_col]).strip()
            if ref and ref.lower() not in ('', 'none'):
                reference = ref

        transactions.append(Transaction(
            date=date_str,
            description=description,
            debit=debit,
            credit=credit,
            balance=balance,
            reference=reference,
            source_line=" | ".join(str(c) for c in row),
        ))

    return transactions


# ─── Format detection ─────────────────────────────────────────────────────────

def _detect_format(col_map: Dict, rows: List[List[str]], header_idx: int) -> str:
    """
    Detect which parsing strategy to use based on column mapping and data shape.

    Returns:
      "signed_amount" - PeoplesSouth/Sneads: Date|Desc|Amount with signed values
      "multicolumn"   - MTD-style: Date|Check#|TranCode|Desc|Amount|Balance
      "standard"      - Standard: separate debit/credit/withdrawal/deposit cols
    """
    has_amount = 'amount' in col_map
    has_debit = 'debit' in col_map
    has_credit = 'credit' in col_map
    has_check = 'check_number' in col_map
    has_tran_code = 'tran_code' in col_map

    if has_check or has_tran_code:
        return "multicolumn"

    if has_amount and not has_debit and not has_credit:
        # Single amount column – check if data rows have an extra trailing
        # column (running balance) beyond the header columns.
        header_cols = len(rows[header_idx]) if header_idx < len(rows) else 3
        data_rows = rows[header_idx + 1: header_idx + 20]
        wider_count = sum(1 for r in data_rows if len(r) > header_cols and r)
        if wider_count > len(data_rows) * 0.3:
            return "signed_amount"
        return "signed_amount"  # Default for single-amount format

    if has_debit and has_credit:
        return "standard"

    return "standard"


#Core processing pipeline

def process_single_statement(file_path: Path) -> StatementResult:
    warnings: List[str] = []

    # Step 1: Detect PDF type
    suffix = file_path.suffix.lower()
    is_image = suffix in {'.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif'}

    if is_image:
        pdf_type = "scanned"
    else:
        pdf_type = detect_pdf_type(file_path)

    LOGGER.info(f"[{file_path.name}] type={pdf_type}")

    # Step 2: Extract Rows (digital or OCR)
    rows: List[List[str]] = []

    if pdf_type == "digital":
        try:
            rows = extract_with_pdfplumber(file_path)
            LOGGER.info(f"[{file_path.name}] pdfplumber → {len(rows)} rows")
        except Exception as e:
            LOGGER.error(f"pdfplumber failed: {e}")
            warnings.append(f"Digital extraction failed, falling back to OCR: {e}")
            pdf_type = "scanned"

    if pdf_type == "scanned" or not rows:
        try:
            images = preprocess_scanned_pdf(file_path, dpi=300)
            for img in images:
                ocr_rows = extract_ocr_rows(img)
                if ocr_rows:
                    rows.extend(ocr_rows)
                else:
                    text = run_paddleocr_structure(img)
                    if text:
                        rows.extend(parse_ocr_text_to_rows(text))
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

    # Step 2b: Detect statement period from preamble for date resolution
    stmt_year, stmt_month = detect_statement_period(rows)
    LOGGER.info(f"[{file_path.name}] statement_period year={stmt_year} month={stmt_month}")

    # Step 2c: Try additions/subtractions format first (US Bank style)
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

    # Step 3: Find header row
    header_idx = detect_header_row(rows)
    if header_idx is None:
        warnings.append("Header row not detected – using row 0")
        header_idx = 0

    header_row = rows[header_idx]
    LOGGER.info(f"[{file_path.name}] header={header_row}")

    # Step 4: Map columns
    col_map = map_columns(header_row)
    LOGGER.info(f"[{file_path.name}] col_map={col_map}")

    if not col_map:
        warnings.append("Column mapping failed – attempting line-by-line parse")
        # Fall back to line-by-line heuristic parse
        data_rows = rows[header_idx + 1:]
        transactions = _parse_lines_heuristic(
            data_rows, file_path.name, statement_year=stmt_year
        )
        transactions.extend(_parse_check_detail_rows(rows, statement_year=stmt_year))
        confidence = calculate_confidence([t.dict() for t in transactions])
        raw_text = "\n".join(" | ".join(r) for r in rows[:20])
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

    # Step 5: Detect format and apply the right parser
    fmt = _detect_format(col_map, rows, header_idx)
    LOGGER.info(f"[{file_path.name}] format={fmt}")

    if fmt == "signed_amount":
        transactions = _parse_signed_amount_rows(
            rows, col_map, header_idx, statement_year=stmt_year
        )
        transactions.extend(_parse_check_detail_rows(rows, statement_year=stmt_year))
        confidence = calculate_confidence([t.dict() for t in transactions])
        raw_text = "\n".join(" | ".join(str(c) for c in r) for r in rows[:20])
        LOGGER.info(
            f"[{file_path.name}] signed_amount → {len(transactions)} transactions"
        )
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
        LOGGER.info(
            f"[{file_path.name}] multicolumn → {len(transactions)} transactions"
        )
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

    # ── Standard format (separate debit/credit columns) ──
    data_rows = rows[header_idx + 1:]

    # Step 5b: Merge wrapped rows
    date_col = col_map.get('date')
    if date_col is not None:
        data_rows = merge_wrapped_rows(data_rows, date_col)

    # Auto-detect balance column from data if not in header
    balance_col = detect_balance_column_from_data(data_rows, col_map)
    if balance_col is not None and 'balance' not in col_map:
        col_map['balance'] = balance_col

    # Step 6: Parse transactions
    transactions: List[Transaction] = []
    rows_processed = rows_with_dates = 0

    for row in data_rows:
        if not row or not any(str(c).strip() for c in row):
            continue
        rows_processed += 1

        # Date
        date_str: Optional[str] = None
        if date_col is not None and date_col < len(row):
            date_str = parse_date(
                str(row[date_col]), statement_year=stmt_year
            )
        if date_str:
            rows_with_dates += 1
        else:
            continue  # skip non-transaction rows

        # Description
        desc = ""
        if 'description' in col_map and col_map['description'] < len(row):
            desc = str(row[col_map['description']]).strip()
        if not desc:
            desc = " ".join(str(c) for c in row).strip()

        # Amounts
        debit, credit = classify_debit_credit(
            row, col_map, balance_col=col_map.get('balance')
        )

        if debit is None and credit is None:
            continue

        # Balance
        balance: Optional[float] = None
        if 'balance' in col_map and col_map['balance'] < len(row):
            balance = clean_amount(str(row[col_map['balance']]))
            if balance is not None:
                balance = abs(balance)

        # Reference
        reference: Optional[str] = None
        ref_col = col_map.get('reference') or col_map.get('check_number')
        if ref_col is not None and ref_col < len(row):
            reference = str(row[ref_col]).strip() or None

        transactions.append(Transaction(
            date=date_str,
            description=desc,
            debit=debit,
            credit=credit,
            balance=balance,
            reference=reference,
            source_line=" | ".join(str(c) for c in row),
        ))

    transactions.extend(_parse_check_detail_rows(rows, statement_year=stmt_year))

    # Step 7: Confidence + summary
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


# Heuristic line parser (fallback when no header found)

def _parse_lines_heuristic(
    rows: List[List[str]],
    filename: str,
    *,
    statement_year: Optional[int] = None,
) -> List[Transaction]:
    """
    Last-resort parser: scan every cell for a date; if found treat the row
    as a transaction and infer amounts from signed/dollar values.
    Works well for BancFirst-style flat text where columns aren't aligned.
    """
    transactions: List[Transaction] = []

    for row in rows:
        if not row:
            continue

        full_line = " ".join(str(c) for c in row)

        # Find date anywhere in the row
        date_str: Optional[str] = None
        for cell in row:
            date_str = parse_date(str(cell), statement_year=statement_year)
            if date_str:
                break
        if not date_str:
            # Try extracting date from the start of cell 0
            date_str, _ = _split_date_from_cell(
                str(row[0]), statement_year=statement_year
            )
        if not date_str:
            continue

        # Description: longest non-date, non-amount cell
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

        # Amounts: collect all numeric values
        amounts = []
        for cell in row:
            v = clean_amount(str(cell))
            if v is not None:
                amounts.append(v)

        debit: Optional[float] = None
        credit: Optional[float] = None
        balance: Optional[float] = None

        if len(amounts) >= 3:
            # Likely: withdrawal, deposit, balance
            # Negative = debit, positive = credit, last = balance
            balance = abs(amounts[-1])
            for v in amounts[:-1]:
                if v < 0:
                    debit = abs(v)
                elif v > 0:
                    credit = v
        elif len(amounts) == 2:
            balance = abs(amounts[-1])
            v = amounts[0]
            if v < 0:
                debit = abs(v)
            else:
                # Use keywords to determine direction
                row_up = full_line.upper()
                if re.search(
                    r'\b(WITHDRAWAL|DEBIT|PURCHASE|CHARGE|FEE|PAYMENT|'
                    r'TRANSFER\s*TO|POS\s*DEB|CHECK)\b', row_up
                ):
                    debit = abs(v)
                else:
                    credit = v
        elif len(amounts) == 1:
            v = amounts[0]
            row_up = full_line.upper()
            if v < 0 or re.search(
                r'\b(WITHDRAWAL|DEBIT|PURCHASE|CHARGE|FEE|PAYMENT|'
                r'TRANSFER\s*TO|POS\s*DEB|CHECK)\b', row_up
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
            reference=None,
            source_line=full_line,
        ))

    return transactions


#  Additions/Subtractions format parser (US Bank style)

def _parse_additions_subtractions_rows(
    rows: List[List[str]],
    *,
    statement_year: Optional[int] = None,
) -> List[Transaction]:
    """
    Parse the "Date | Description | Additions | Subtractions" table format.
    The header may appear as a single row or be split across two rows.
    """
    transactions: List[Transaction] = []
    in_activity_table = False

    for row in rows:
        row_text = " ".join(str(c) for c in row).strip()
        row_lower = row_text.lower()

        # Detect the activity table header – allow partial matches
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
                previous.source_line = f"{previous.source_line} | {row_text}"
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
            reference=None,
            source_line=" | ".join(str(c) for c in row),
        ))

    return transactions


# Check detail rows parser 
def _parse_check_detail_rows(
    rows: List[List[str]],
    *,
    statement_year: Optional[int] = None,
) -> List[Transaction]:
    """Parse check-detail rows like Number/Date/Amount pairs as debits."""
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
                reference=check_number,
                source_line=match.group(0),
            ))

    return transactions


# API endpoints

@router.post("/process", response_model=OCRResponse)
async def process_documents(files: List[UploadFile] = File(...)):
    """
    Process bank statement documents without duplicate checking.
    Use /process-with-duplicate-check for duplicate detection.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    results: List[StatementResult] = []

    for upload in files:
        target_path = UPLOAD_DIR / upload.filename
        try:
            await write_file(upload, target_path)
            result = process_single_statement(target_path)
            results.append(result)
            LOGGER.info(
                f"Done: {upload.filename} → "
                f"{len(result.transactions)} transactions, "
                f"confidence={result.confidence}"
            )
        except Exception as exc:
            LOGGER.error(f"Failed: {upload.filename}: {exc}", exc_info=True)
            results.append(StatementResult(
                filename=upload.filename,
                transactions=[],
                confidence=0.0,
                pdf_type="unknown",
                warnings=[f"Processing failed: {exc}"],
                raw_text="",
            ))
        finally:
            try:
                if target_path.exists():
                    target_path.unlink()
            except Exception:
                pass

    return OCRResponse(status="success", documents=results)


@router.post("/process-with-duplicate-check", response_model=OCRResponse)
async def process_documents_with_duplicate_check(
    files: List[UploadFile] = File(...),
):
    """
    Process bank statement documents WITH duplicate detection.

    This endpoint:
    1. Generates file hash before processing
    2. Processes the document
    3. Generates content hash after extraction
    4. Returns duplicate detection information

    The frontend/backend should then check these hashes against the database
    before saving to prevent duplicates.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    results: List[StatementResult] = []

    for upload in files:
        target_path = UPLOAD_DIR / upload.filename
        try:
            # Write file to disk
            await write_file(upload, target_path)

            # Generate file hash BEFORE processing
            file_hash = generate_file_hash(target_path)
            LOGGER.info(f"File hash for {upload.filename}: {file_hash[:16]}...")

            # Process the statement
            result = process_single_statement(target_path)

            # Generate content hash and fingerprint AFTER processing
            metadata = {
                "bank_name": result.bank_name,
                "account_number": result.account_number,
                "current_balance": result.current_balance,
            }
            content_hash = generate_content_hash(result.transactions, metadata)
            fingerprint = generate_transaction_fingerprint(result.transactions)

            # Update result with hash information
            result.file_hash = file_hash
            result.content_hash = content_hash
            result.fingerprint = fingerprint

            results.append(result)
            LOGGER.info(
                f"Done: {upload.filename} → "
                f"{len(result.transactions)} transactions, "
                f"confidence={result.confidence}, "
                f"file_hash={file_hash[:16]}..., "
                f"content_hash={content_hash[:16]}..."
            )
        except Exception as exc:
            LOGGER.error(f"Failed: {upload.filename}: {exc}", exc_info=True)
            results.append(StatementResult(
                filename=upload.filename,
                transactions=[],
                confidence=0.0,
                pdf_type="unknown",
                warnings=[f"Processing failed: {exc}"],
                raw_text="",
            ))
        finally:
            try:
                if target_path.exists():
                    target_path.unlink()
            except Exception:
                pass

    return OCRResponse(status="success", documents=results)


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "bank-ocr-python"}
