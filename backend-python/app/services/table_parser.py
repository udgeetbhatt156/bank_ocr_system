"""
Table Parser Service
Maps columns from various bank statement formats worldwide
Supports: BMO, Suncoast, US Bank, HDFC, ICICI, Axis, SBI, YES Bank, Bank of Baroda, etc.
"""
import re
from typing import Dict, List, Optional

# ─── Column patterns ────────────────────────────────────────────────────────
# Uses partial matching (no ^ / $ anchors) so "Transaction description" still
# maps to 'description', "Post Date" maps to 'date', etc.
COLUMN_PATTERNS = {
    'date': [
        r'\bpost\s*date\b',
        r'\bdate\b',
        r'\btxn\s*date\b',
        r'\btransaction\s*date\b',
        r'\bvalue\s*date\b',
        r'\bposting\s*date\b',
        r'\beff\s*date\b',
        r'\beffective\s*date\b',
        r'\btrans\s*date\b',
    ],
    'description': [
        r'\btransaction\s*description\b',
        r'\btransaction\s*details\b',
        r'\bdescription\b',
        r'\bparticulars\b',
        r'\bnarration\b',
        r'\bremarks\b',
        r'\bdetails\b',
        r'\bmemo\b',
    ],
    'debit': [
        r'\bwithdrawal\b',
        r'\bwithdrawals\b',
        r'\bsubtraction\b',
        r'\bsubtractions\b',
        r'\bdebit\b',
        r'\bdr\b',
        r'\bdebit\s*amount\b',
        r'\bpaid\s*out\b',
        r'\bamount\s*debited\b',
        r'\bmoney\s*out\b',
    ],
    'credit': [
        r'\bdeposit\b',
        r'\bdeposits\b',
        r'\baddition\b',
        r'\badditions\b',
        r'\bcredit\b',
        r'\bcr\b',
        r'\bcredit\s*amount\b',
        r'\bpaid\s*in\b',
        r'\bamount\s*credited\b',
        r'\bmoney\s*in\b',
    ],
    'balance': [
        r'\bnew\s*balance\b',
        r'\bclosing\s*balance\b',
        r'\bavailable\s*balance\b',
        r'\bbalance\b',
        r'\brunning\s*balance\b',
    ],
    'reference': [
        r'\bref(?:erence)?\s*(?:no|num|number|#)?\b',
        r'\bcheque\s*(?:no|num|number)?\b',
        r'\bcheck\s*(?:no|num|number)?\b',
        r'\btransaction\s*id\b',
        r'\butr\b',
        r'\bcard\s*(?:no|number)?\b',
        r'\binstrument\s*no\b',
    ],
    'amount': [
        r'^amount$',
        r'\btransaction\s*amount\b',
    ],
}


def map_columns(header_row: List[str]) -> Dict[str, int]:
    """Map column headers to their indices."""
    column_map = {}

    for idx, header in enumerate(header_row):
        if not header:
            continue
        header_lower = header.lower().strip()

        for col_type, patterns in COLUMN_PATTERNS.items():
            if col_type in column_map:
                continue
            for pattern in patterns:
                if re.search(pattern, header_lower, re.IGNORECASE):
                    column_map[col_type] = idx
                    break

    return column_map


def merge_wrapped_rows(rows: List[List[str]], date_col_idx: Optional[int] = None) -> List[List[str]]:
    """
    Merge continuation rows (no date) into the previous transaction row.
    Common in BMO, YES Bank, Bank of Baroda statements.
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
                # Merge description text
                desc_idx = date_col_idx + 1
                if desc_idx < len(row) and desc_idx < len(nxt) and nxt[desc_idx].strip():
                    row[desc_idx] = row[desc_idx].rstrip() + " " + nxt[desc_idx].strip()
                i += 1
            merged.append(row)
        # else: orphan row without date – skip
        i += 1

    return merged


def detect_header_row(rows: List[List[str]]) -> Optional[int]:
    """
    Find the header row by looking for keyword density.
    Searches first 20 rows to handle statements with long preambles.
    """
    header_keywords = [
        'date', 'description', 'debit', 'credit', 'balance',
        'particulars', 'withdrawal', 'deposit', 'amount', 'narration',
        'transaction', 'details', 'withdrawal', 'post', 'subtractions',
        'additions',
    ]

    best_idx = None
    best_score = 0

    for idx, row in enumerate(rows[:80]):
        row_text = ' '.join(str(c) for c in row).lower()
        score = sum(1 for kw in header_keywords if re.search(r'\b' + kw + r'\b', row_text))
        if score > best_score:
            best_score = score
            best_idx = idx

    # Require at least 2 keyword matches
    return best_idx if best_score >= 2 else None
