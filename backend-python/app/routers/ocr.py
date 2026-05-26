"""
OCR Router - Main processing pipeline
Handles digital PDFs, scanned PDFs, and image files.
Supports BMO, Suncoast, US Bank, HDFC, ICICI, YES Bank, Bank of Baroda, etc.
"""
from pathlib import Path
from typing import List, Optional
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
from app.services.table_parser import map_columns, merge_wrapped_rows, detect_header_row
from app.services.postprocessor import (
    clean_amount, parse_date, classify_debit_credit, calculate_confidence
)

router = APIRouter()
LOGGER = logging.getLogger(__name__)


#  File writer 

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
            #  Try structured table extraction first
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    for row in table:
                        cleaned = [str(c).strip() if c else "" for c in row]
                        if any(cleaned):
                            all_rows.append(cleaned)
                continue  # page handled

            # Fall back: reconstruct rows from word positions
            words = page.extract_words(
                x_tolerance=3,
                y_tolerance=3,
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

            # Group words into lines by their top-y coordinate (±3 px)
            lines: dict = {}
            for w in words:
                y_key = round(w['top'] / 3) * 3
                lines.setdefault(y_key, []).append(w)

            for y_key in sorted(lines):
                line_words = sorted(lines[y_key], key=lambda w: w['x0'])
                # Cluster words into columns by x-gap
                cols: List[str] = []
                current = line_words[0]['text']
                for prev, curr in zip(line_words, line_words[1:]):
                    gap = curr['x0'] - prev['x1']
                    if gap > 8:          # column separator
                        cols.append(current.strip())
                        current = curr['text']
                    else:
                        current += ' ' + curr['text']
                cols.append(current.strip())
                if any(cols):
                    all_rows.append(cols)

    return all_rows


# Core processing pipeline

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

    # Step 2: Extract Rows (digittal or OCR)
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
            images = preprocess_scanned_pdf(file_path, dpi=120)
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
        return StatementResult(
            filename=file_path.name, transactions=[],
            confidence=0.0, pdf_type=pdf_type,
            warnings=warnings + ["No data extracted from document"],
            raw_text=""
        )

    add_sub_transactions = _parse_additions_subtractions_rows(rows)
    if add_sub_transactions:
        confidence = calculate_confidence([t.dict() for t in add_sub_transactions])
        raw_text = "\n".join(" | ".join(str(c) for c in r) for r in rows[:20])
        return StatementResult(
            filename=file_path.name,
            transactions=add_sub_transactions,
            confidence=confidence,
            pdf_type=pdf_type,
            warnings=warnings,
            raw_text=raw_text,
        )

    # Step 3: Find header row
    header_idx = detect_header_row(rows)
    if header_idx is None:
        warnings.append("Header row not detected – using row 0")
        header_idx = 0

    header_row = rows[header_idx]
    data_rows  = rows[header_idx + 1:]
    LOGGER.info(f"[{file_path.name}] header={header_row}")

    # Step 4: Map columns 
    col_map = map_columns(header_row)
    LOGGER.info(f"[{file_path.name}] col_map={col_map}")

    if not col_map:
        warnings.append("Column mapping failed attempting line-by-line parse")
        # Fall back to line-by-line heuristic parse
        transactions = _parse_lines_heuristic(data_rows, file_path.name)
        confidence = calculate_confidence([t.dict() for t in transactions])
        raw_text = "\n".join(" | ".join(r) for r in rows[:20])
        LOGGER.info(f"[{file_path.name}] heuristic → {len(transactions)} transactions")
        return StatementResult(
            filename=file_path.name,
            transactions=transactions,
            confidence=confidence,
            pdf_type=pdf_type,
            warnings=warnings,
            raw_text=raw_text,
        )

    #  Step 5: Merge wrapped rows 
    date_col = col_map.get('date')
    if date_col is not None:
        data_rows = merge_wrapped_rows(data_rows, date_col)

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
            date_str = parse_date(str(row[date_col]))
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
        debit, credit = classify_debit_credit(row, col_map)

        # Balance
        balance: Optional[float] = None
        if 'balance' in col_map and col_map['balance'] < len(row):
            balance = clean_amount(str(row[col_map['balance']]))

        # Reference
        reference: Optional[str] = None
        if 'reference' in col_map and col_map['reference'] < len(row):
            reference = str(row[col_map['reference']]).strip() or None

        transactions.append(Transaction(
            date=date_str,
            description=desc,
            debit=debit,
            credit=credit,
            balance=balance,
            reference=reference,
            source_line=" | ".join(str(c) for c in row),
        ))

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
    return StatementResult(
        filename=file_path.name,
        transactions=transactions,
        confidence=confidence,
        pdf_type=pdf_type,
        warnings=warnings,
        raw_text=raw_text,
    )


# Heuristic line parser (fallback when no header found)

def _parse_lines_heuristic(rows: List[List[str]], filename: str) -> List[Transaction]:
    """
    Last-resort parser: scan every cell for a date; if found treat the row
    as a transaction and infer amounts from signed/dollar values.
    Works well for BMO-style flat text where columns aren't aligned.
    """
    transactions: List[Transaction] = []

    for row in rows:
        if not row:
            continue

        full_line = " ".join(str(c) for c in row)

        # Find date anywhere in the row
        date_str: Optional[str] = None
        for cell in row:
            date_str = parse_date(str(cell))
            if date_str:
                break
        if not date_str:
            continue

        # Description: longest non-date, non-amount cell
        desc_candidates = []
        for cell in row:
            s = str(cell).strip()
            if not s:
                continue
            if parse_date(s):
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
            balance = amounts[-1]
            for v in amounts[:-1]:
                if v < 0:
                    debit = abs(v)
                elif v > 0:
                    credit = v
        elif len(amounts) == 2:
            balance = amounts[-1]
            v = amounts[0]
            if v < 0:
                debit = abs(v)
            else:
                credit = v
        elif len(amounts) == 1:
            v = amounts[0]
            row_up = full_line.upper()
            if v < 0 or re.search(r'\b(WITHDRAWAL|DEBIT|PURCHASE|CHARGE|FEE|PAYMENT)\b', row_up):
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


def _parse_additions_subtractions_rows(rows: List[List[str]]) -> List[Transaction]:
    transactions: List[Transaction] = []
    in_activity_table = False

    for row in rows:
        row_text = " ".join(str(c) for c in row).strip()
        row_lower = row_text.lower()

        has_add_sub_header = (
            "date" in row_lower
            and "description" in row_lower
            and "additions" in row_lower
            and "subtractions" in row_lower
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

        date_str = parse_date(str(row[0]))
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


# API endpoint 

@router.post("/process", response_model=OCRResponse)
async def process_documents(files: List[UploadFile] = File(...)):
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


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "bank-ocr-python"}
