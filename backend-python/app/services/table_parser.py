"""
Table Parser Service
Maps columns from various bank statement formats worldwide.

Supports: PeoplesSouth, BancFirst, BMO, Suncoast, US Bank, HDFC, ICICI,
Axis, SBI, YES Bank, Bank of Baroda, Chase, Wells Fargo, etc.
"""
import re
from typing import Dict, List, Optional, Tuple

# ─── Column patterns ────────────────────────────────────────────────────────
# Uses partial matching (no ^ / $ anchors) so "Transaction description" still
# maps to 'description', "Post Date" maps to 'date', etc.
COLUMN_PATTERNS = {
    'date': [
        r'\bpost\s*date\b',
        r'\bposted\s*date\b',
        r'\bposted\b',
        r'\bdate\b',
        r'\btxn\s*date\b',
        r'\btransaction\s*date\b',
        r'\bvalue\s*date\b',
        r'\bposting\s*date\b',
        r'\beff(?:ective)?\s*date\b',
        r'\btrans\s*date\b',
    ],
    'description': [
        r'\btransaction\s*description\b',
        r'\btransaction\s*details\b',
        r'\btransaction\s*detail\b',
        r'\bdescription\b',
        r'\bparticulars\b',
        r'\bnarration\b',
        r'\bremarks\b',
        r'\bdetails\b',
        r'\bmemo\b',
        r'\bactivity\b',
    ],
    'debit': [
        r'\bwithdrawals?\s*/\s*debits?\b',
        r'\bwithdrawal\b',
        r'\bwithdrawals\b',
        r'\bsubtraction\b',
        r'\bsubtractions\b',
        r'\bdebits\b',
        r'\bdebit\s*amount\b',
        r'\bdebit\b',
        r'\bdr\b',
        r'\bpaid\s*out\b',
        r'\bamount\s*debited\b',
        r'\bmoney\s*out\b',
    ],
    'credit': [
        r'\bdeposits?\s*/\s*credits?\b',
        r'\bdeposit\b',
        r'\bdeposits\b',
        r'\baddition\b',
        r'\badditions\b',
        r'\bcredits\b',
        r'\bcredit\s*amount\b',
        r'\bcredit\b',
        r'\bcr\b',
        r'\bpaid\s*in\b',
        r'\bamount\s*credited\b',
        r'\bmoney\s*in\b',
    ],
    'balance': [
        r'\bending\s+daily\s+balance\b',
        r'\bnew\s*balance\b',
        r'\bclosing\s*balance\b',
        r'\bavailable\s*balance\b',
        r'\brunning\s*balance\b',
        r'\bdaily\s*balance\b',
        r'\bend\s*bal(?:ance)?\b',
        r'\bbalance\b',
    ],
    'check_number': [
        r'\bcheck\s*[#]',
        r'\bcheck\s*(?:no|num|number|nmbr)\b',
        r'\bchk\s*(?:no|num|number|#)?\b',
        r'\bcheck\s+number\b',
    ],
    'tran_code': [
        r'\btran\s*code\b',
        r'\btran(?:saction)?\s*type\b',
    ],
    'amount': [
        r'\bamount\b',
        r'\btransaction\s*amount\b',
    ],
}

# Quick regexes for header-row scoring penalties
_DATE_LIKE_RE = re.compile(
    r'\b\d{1,2}[/\-\.]\d{1,2}(?:[/\-\.]\d{2,4})?\b'
)
_AMOUNT_LIKE_RE = re.compile(
    r'[\$₹]\s*[\d,]+\.?\d*|^\(?\$?[\d,]+\.\d{2}\)?$'
)


def _normalize_header_text(value: str) -> str:
    text = re.sub(r'\s+', ' ', str(value or '')).strip().lower()
    replacements = {
        "tran saction": "transaction",
        "trans action": "transaction",
        "desc ription": "description",
        "de script ion": "description",
        "amt": "amount",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r'\bsaction\s+detail\b', 'transaction detail', text)
    text = re.sub(r'\bription\b', 'description', text)
    text = re.sub(r'amount\s*\(?\$?\)?', 'amount', text)
    text = re.sub(r'balance\s*\(?\$?\)?', 'balance', text)
    return text


def normalize_header_row(header_row: List[str]) -> List[str]:
    """Normalize OCR/pdfplumber-fragmented header cells while preserving indices."""
    normalized = [_normalize_header_text(cell) for cell in header_row]
    result = list(normalized)
    for idx, text in enumerate(normalized):
        nxt = normalized[idx + 1] if idx + 1 < len(normalized) else ""
        combo = f"{text} {nxt}".strip()
        if re.search(r'\bdate\s+desc(?:ription)?\b', combo):
            result[idx] = "date"
            if idx + 1 < len(result):
                result[idx + 1] = "description"
        elif "date tran" in combo or "transaction detail" in combo:
            if "date" in text:
                result[idx] = "date"
            if idx + 1 < len(result):
                result[idx + 1] = "transaction detail"
    return result


def map_columns(header_row: List[str]) -> Dict[str, int]:
    """
    Map column headers to their indices.

    Prevents the same cell index from being claimed by multiple column types
    (e.g. a cell saying "Deposits & Withdrawals" would otherwise match both
    'debit' and 'credit').
    """
    column_map: Dict[str, int] = {}
    used_indices: set = set()

    normalized_row = normalize_header_row(header_row)

    for idx, header in enumerate(normalized_row):
        if not header:
            continue
        header_lower = header.lower().strip()

        for col_type, patterns in COLUMN_PATTERNS.items():
            if col_type in column_map:
                continue
            if idx in used_indices:
                # This cell is already claimed by another type – skip
                continue
            for pattern in patterns:
                if re.search(pattern, header_lower, re.IGNORECASE):
                    column_map[col_type] = idx
                    used_indices.add(idx)
                    break

    return column_map


def detect_balance_column_from_data(
    data_rows: List[List[str]],
    col_map: Dict[str, int],
) -> Optional[int]:
    """
    If the header defines fewer columns than the data rows consistently have,
    the extra trailing column is almost always the running balance.

    Returns the balance column index, or None.
    """
    if 'balance' in col_map:
        return col_map['balance']

    mapped_max = max(col_map.values()) if col_map else -1

    # Check if a majority of data rows have at least one more column
    extra_col_count = 0
    sample_size = min(len(data_rows), 30)
    for row in data_rows[:sample_size]:
        if len(row) > mapped_max + 1:
            extra_col_count += 1

    if extra_col_count >= sample_size * 0.5:
        # The trailing column is likely the running balance
        return mapped_max + 1

    return None


def merge_wrapped_rows(
    rows: List[List[str]], date_col_idx: Optional[int] = None
) -> List[List[str]]:
    """
    Merge continuation rows (no date) into the previous transaction row.
    Common in BMO, YES Bank, Bank of Baroda, PeoplesSouth statements.
    """
    if not rows or date_col_idx is None:
        return rows

    from app.services.postprocessor import parse_date

    merged: List[List[str]] = []
    i = 0
    while i < len(rows):
        row = list(rows[i])  # copy
        date_val = row[date_col_idx] if date_col_idx < len(row) else ""
        has_date = bool(parse_date(date_val))

        if has_date:
            # Absorb following continuation rows
            while i + 1 < len(rows):
                nxt = rows[i + 1]
                nxt_date = nxt[date_col_idx] if date_col_idx < len(nxt) else ""
                if parse_date(nxt_date):
                    break  # next row is a real transaction
                # Merge description text (try column after date first)
                desc_idx = date_col_idx + 1
                if desc_idx < len(row) and desc_idx < len(nxt) and nxt[desc_idx].strip():
                    row[desc_idx] = row[desc_idx].rstrip() + " " + nxt[desc_idx].strip()
                elif nxt:
                    # Merge any non-empty text from the continuation row
                    extra_text = " ".join(
                        str(c).strip() for c in nxt if str(c).strip()
                    )
                    if extra_text and desc_idx < len(row):
                        row[desc_idx] = row[desc_idx].rstrip() + " " + extra_text
                i += 1
            merged.append(row)
        # else: orphan row without date – skip
        i += 1

    return merged


def detect_header_row(rows: List[List[str]]) -> Optional[int]:
    """
    Find the header row by looking for keyword density.

    Improvements over the naïve keyword-count approach:
      - Bonus when "date" + "description"/"activity" appear together
      - Penalty when a row contains actual date values or dollar amounts
        (those are data rows, not headers)
      - Searches first 80 rows to handle statements with long preambles
    """
    header_keywords = [
        'date', 'description', 'debit', 'credit', 'balance',
        'particulars', 'withdrawal', 'deposit', 'amount', 'narration',
        'transaction', 'details', 'subtractions', 'additions',
        'check', 'posted', 'effective', 'activity', 'tran',
        'debits', 'credits', 'withdrawals', 'deposits',
    ]

    best_idx: Optional[int] = None
    best_score = 0

    for idx, row in enumerate(rows[:80]):
        normalized_row = normalize_header_row(row)
        row_text = ' '.join(str(c) for c in normalized_row).lower()
        score = sum(
            1 for kw in header_keywords
            if re.search(r'\b' + kw + r'\b', row_text)
        )

        # Bonus: "date" AND ("description" or "activity") together is very
        # strong evidence of a header row.
        has_date_kw = bool(re.search(r'\bdate\b', row_text))
        has_desc_kw = bool(
            re.search(r'\bdescription\b|\bactivity\b|\bparticulars\b', row_text)
        )
        if has_date_kw and has_desc_kw:
            score += 3

        # Penalty: rows that contain actual date values or dollar amounts
        # are very likely data rows, not headers.
        for cell in row:
            s = str(cell).strip()
            if _DATE_LIKE_RE.search(s) and len(s) < 12:
                # Short date-like value (e.g. "04/01/2026") → likely data
                score -= 2
                break
            if _AMOUNT_LIKE_RE.search(s):
                score -= 1

        if score > best_score:
            best_score = score
            best_idx = idx

    # Require at least 2 keyword matches (after penalties)
    return best_idx if best_score >= 2 else None
