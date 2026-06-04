"""
Post-processing Service
Cleans amounts, dates, and classifies debit/credit transactions.

Handles real-world formats from:
  - PeoplesSouth  : "1/02", signed amounts "7.37-", "($234.18)", balance trailing
  - BancFirst     : "12/01 190.00 DEPOSIT", flat-text rows
  - BMO Bank      : "Jul 01", "$1,234.56", "-$700.00"
  - Suncoast CU   : "04/01/2025", signed amounts
  - US Bank       : "10/02", plain numbers
  - HDFC/ICICI    : "01/01/2024", "₹1,234.56"
  - YES Bank      : "10/11/2018", colored amounts
  - Bank of Baroda: "24-04-2023"
  - First Bank    : "2003-10-08"
"""
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Current year used to fill in 2-part dates like "Jul 01"
_CURRENT_YEAR = datetime.now().year

# Month abbreviation → number
_MONTH_MAP = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
    'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}

# OCR common character misreads: letter → digit
_OCR_DIGIT_FIXES = str.maketrans({
    'O': '0', 'o': '0',
    'l': '1', 'I': '1', 'i': '1',
    'S': '5', 's': '5',
    'B': '8',
    'G': '6', 'g': '6',
    'Z': '2', 'z': '2',
    'T': '7',
})


# Amount cleaning 
def clean_amount(raw_value: str) -> Optional[float]:
    """
    Parse an amount string into a float.

    Handles:
      $1,234.56  -$700.00  ₹1,234.56  1,234.56 Dr  1234.56 Cr
      (1,234.56)  +1234    $1,234.56-  1.234,56 (European)
      7.37-  ($234.18)  *1234.56  #1234.56
    Returns signed value (negative = debit context).
    """
    if not raw_value or not isinstance(raw_value, str):
        return None

    s = raw_value.strip()

    # Parentheses → negative  e.g. (1,234.56) or ($1,234.56)
    is_paren_negative = s.startswith('(') and s.endswith(')')
    if is_paren_negative:
        s = s[1:-1]

    # ── Strip currency symbols and common prefixes FIRST ──
    # This must happen BEFORE the letter/slash check so "$" doesn't cause
    # false positives.
    s = re.sub(r'Rs\.?|INR', '', s, flags=re.IGNORECASE)
    s = re.sub(r'[$₹€£¥]', '', s)

    # Strip Dr / Cr suffixes
    s = re.sub(r'\s*(Dr|Cr|DR|CR)\.?$', '', s, flags=re.IGNORECASE)

    # Remove leading/trailing whitespace, asterisks, hashes (scan artifacts)
    s = s.strip().strip('*#').strip()

    # Avoid treating masked accounts, references, or narration text as money
    # when OCR places them near amount columns.
    if re.search(r'(?:x{2,}|\*{2,})\d{3,}', s, flags=re.IGNORECASE):
        return None

    # ── OCR misread correction for digits ──
    # Only apply if the string looks mostly numeric already (has at least
    # one real digit and is short enough to be an amount).
    if re.search(r'\d', s) and len(s) <= 20:
        # Fix common OCR letter→digit errors but only for characters that
        # are surrounded by digits or separators.
        corrected = []
        for i, ch in enumerate(s):
            if ch in _OCR_DIGIT_FIXES and ch.isalpha():
                # Check context: adjacent to digit or separator?
                prev_ok = (i == 0) or s[i - 1].isdigit() or s[i - 1] in '.,- '
                next_ok = (i == len(s) - 1) or s[i + 1].isdigit() or s[i + 1] in '.,- '
                if prev_ok and next_ok:
                    corrected.append(chr(_OCR_DIGIT_FIXES[ord(ch)]))
                else:
                    corrected.append(ch)
            else:
                corrected.append(ch)
        s = ''.join(corrected)

    # ── Reject if still contains letters or slashes ──
    # After currency stripping and OCR correction, genuine amounts should
    # be purely numeric (with separators).
    if re.search(r'[A-Za-z/]', s):
        return None

    # Reject very long digit-only strings (account numbers, not amounts).
    # Allow up to 12 digits for large business account balances.
    digits_only = re.sub(r'[^0-9]', '', s)
    if len(digits_only) > 12:
        return None

    # Handle leading/trailing minus/plus. Some bank statements use "$123-".
    negative = s.startswith('-') or s.endswith('-')
    s = s.strip('+-').strip()

    # Remove thousands separators (commas) – but keep decimal point
    # Also handle European format: 1.234,56 → 1234.56
    if re.search(r'\d,\d{3}[,\d]', s):          # 1,234 or 1,234,567
        s = s.replace(',', '')
    elif re.search(r'\d\.\d{3},\d{2}$', s):      # European 1.234,56
        s = s.replace('.', '').replace(',', '.')
    else:
        s = s.replace(',', '')

    # Keep only digits and decimal point (preserve the dot!)
    s = re.sub(r'[^\d.]', '', s)

    if not s or s in {'.'}:
        return None

    try:
        val = float(s)
        if is_paren_negative or negative:
            val = -val
        return val
    except ValueError:
        return None


# Date parsing 

def parse_date(
    raw_text: str,
    *,
    statement_year: Optional[int] = None,
    statement_month: Optional[int] = None,
) -> Optional[str]:
    """
    Parse a date string into ISO format (YYYY-MM-DD).

    Args:
        raw_text: The raw date text from the PDF/OCR.
        statement_year: Optional year context from the statement period.
            When set, short dates like "12/01" will use this year instead of
            the current year.
        statement_month: Optional month context for resolving ambiguous
            short dates.

    Supported formats (all real-world examples from uploaded statements):
      04/01/2025   MM/DD/YYYY  (Suncoast, US Bank full)
      01/01/2024   DD/MM/YYYY  (HDFC, ICICI)
      10/02        MM/DD       (US Bank short – year inferred)
      02/01        DD/MM       (short)
      Jul 01       Mon DD      (BMO Bank)
      Jul 01, 2025 Mon DD YYYY (BMO with year)
      15-Jan-24    DD-Mon-YY   (HDFC short)
      24-04-2023   DD-MM-YYYY  (Bank of Baroda)
      2003-10-08   YYYY-MM-DD  (First Bank Wiki)
      01.01.2024   DD.MM.YYYY
    """
    if not raw_text or not isinstance(raw_text, str):
        return None

    s = raw_text.strip()

    # OCR correction for date strings 
    # Common: O→0, l→1 in numeric contexts like "O1/O2/2O26"
    if re.search(r'[/\-\.]', s) and len(s) <= 15:
        s = re.sub(r'(?<=\d)[Oo]|[Oo](?=\d)', '0', s)
        s = re.sub(r'(?<=\d)[lI]|[lI](?=\d)', '1', s)

    year_hint = statement_year or _CURRENT_YEAR

    # 1. YYYY-MM-DD
    m = re.search(r'\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b', s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date().isoformat()
        except ValueError:
            pass

    #  2. DD/MM/YYYY or MM/DD/YYYY (4-digit year)
    m = re.search(r'\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})\b', s)
    if m:
        d1, d2, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # If first part > 12 it must be DD
        if d1 > 12:
            try:
                return datetime(yr, d2, d1).date().isoformat()
            except ValueError:
                pass
        # If second part > 12 it must be DD
        elif d2 > 12:
            try:
                return datetime(yr, d1, d2).date().isoformat()
            except ValueError:
                pass
        else:
            # Ambiguous – try MM/DD/YYYY first (US), then DD/MM/YYYY
            for mo, dy in [(d1, d2), (d2, d1)]:
                try:
                    return datetime(yr, mo, dy).date().isoformat()
                except ValueError:
                    continue

    #  3. DD/MM/YY or MM/DD/YY (2-digit year)
    m = re.search(r'\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2})\b', s)
    if m:
        d1, d2, yr2 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        yr = 2000 + yr2 if yr2 < 70 else 1900 + yr2
        if d1 > 12:
            try:
                return datetime(yr, d2, d1).date().isoformat()
            except ValueError:
                pass
        elif d2 > 12:
            try:
                return datetime(yr, d1, d2).date().isoformat()
            except ValueError:
                pass
        else:
            for mo, dy in [(d1, d2), (d2, d1)]:
                try:
                    return datetime(yr, mo, dy).date().isoformat()
                except ValueError:
                    continue

    # 4. "Jul 01" or "Jul 01, 2025"  (BMO Bank style)
    m = re.search(
        r'\b([A-Za-z]{3})\.?\s+(\d{1,2})(?:[,\s]+(\d{4}))?\b', s
    )
    if m:
        mon_str = m.group(1).lower()
        if mon_str in _MONTH_MAP:
            mo = _MONTH_MAP[mon_str]
            dy = int(m.group(2))
            yr = int(m.group(3)) if m.group(3) else year_hint
            try:
                return datetime(yr, mo, dy).date().isoformat()
            except ValueError:
                pass

    # 5. "15-Jan-24" or "15-Jan-2024"  (DD-Mon-YY)
    m = re.search(r'\b(\d{1,2})-([A-Za-z]{3})\.?-(\d{2,4})\b', s)
    if m:
        dy = int(m.group(1))
        mon_str = m.group(2).lower()
        if mon_str in _MONTH_MAP:
            mo = _MONTH_MAP[mon_str]
            yr_raw = int(m.group(3))
            yr = yr_raw if yr_raw > 99 else (2000 + yr_raw if yr_raw < 70 else 1900 + yr_raw)
            try:
                return datetime(yr, mo, dy).date().isoformat()
            except ValueError:
                pass

    # 6. Short date "MM/DD" or "DD/MM" with no year
    m = re.search(r'\b(\d{1,2})[/\-\.](\d{1,2})\b', s)
    if m:
        d1, d2 = int(m.group(1)), int(m.group(2))
        yr = year_hint
        if d1 > 12:
            try:
                return datetime(yr, d2, d1).date().isoformat()
            except ValueError:
                pass
        elif d2 > 12:
            try:
                return datetime(yr, d1, d2).date().isoformat()
            except ValueError:
                pass
        else:
            # Assume MM/DD (US style)
            try:
                return datetime(yr, d1, d2).date().isoformat()
            except ValueError:
                pass

    return None


# Debit / Credit classification 

def classify_debit_credit(
    row: List[str],
    col_map: Dict[str, int],
    *,
    balance_col: Optional[int] = None,
) -> Tuple[Optional[float], Optional[float]]:
    """
    Return (debit, credit) amounts from a data row.

    Handles:
      1. Separate Withdrawal / Deposit columns  (BMO, Suncoast, US Bank)
      2. Single signed Amount column            (PeoplesSouth, Suncoast savings)
      3. Separate Debit / Credit columns        (HDFC, ICICI, YES Bank)
      4. Single Amount with Dr/Cr keyword       (Bank of Baroda)

    The *balance_col* parameter prevents misclassifying the running balance
    as a credit/debit value.
    """
    debit: Optional[float] = None
    credit: Optional[float] = None

    # Format 1: separate withdrawal + deposit columns
    if 'debit' in col_map and 'credit' in col_map:
        w_idx = col_map['debit']
        d_idx = col_map['credit']
        raw_w = row[w_idx] if w_idx < len(row) else ''
        raw_d = row[d_idx] if d_idx < len(row) else ''

        w_val = clean_amount(raw_w)
        d_val = clean_amount(raw_d)

        row_text = ' '.join(str(c) for c in row).upper()
        debit_like = bool(re.search(
            r'\b(WITHDRAWAL|DEBIT|DR|TRANSFER TO|XFER TO|PAYMENT|PMT|'
            r'PURCHASE|CHARGE|FEE|INSUFFICIENT|OVERDRAFT|ACH\s*PAYMENT|'
            r'ACHPAYMENT|PAYPAL|UTIL PAYMT)\b',
            row_text
        ))
        credit_like = bool(re.search(
            r'\b(DEPOSIT|DEP|CREDIT|CR|TRANSFER FROM|XFER FROM|PAID IN|'
            r'BANKCARD|MTOT DEP|ACH CREDIT)\b',
            row_text
        ))

        # Some statements render section tables as Date | Amount | Description
        # under a Deposits/Withdrawals header. When the debit column cell is
        # actually narration, use the row language to decide whether the single
        # amount belongs to debit or credit.
        if w_val is None and d_val is not None and debit_like and not credit_like:
            return abs(d_val), None

        if w_val is not None and w_val != 0:
            debit = abs(w_val)
        if d_val is not None and d_val != 0:
            credit = abs(d_val)

        return debit, credit

    # Format 2: single 'amount' column (signed)
    if 'amount' in col_map:
        a_idx = col_map['amount']
        raw_a = row[a_idx] if a_idx < len(row) else ''
        val = clean_amount(raw_a)

        # Guard: don't confuse the balance column with the amount column.
        # If the mapped amount index is actually pointing at the balance,
        # try the cell just before it.
        if val is not None and balance_col is not None and a_idx == balance_col:
            # The mapped 'amount' column IS the balance – look one cell left
            alt_idx = a_idx - 1
            if 0 <= alt_idx < len(row):
                alt_val = clean_amount(str(row[alt_idx]))
                if alt_val is not None:
                    val = alt_val

        if val is not None:
            if val < 0:
                debit = abs(val)
            else:
                credit = val
        return debit, credit

    # Format 3: scan all cells for signed amounts (excluding balance column)
    row_text = ' '.join(str(c) for c in row).upper()
    amounts = []
    for cell_idx, cell in enumerate(row):
        if balance_col is not None and cell_idx == balance_col:
            continue  # skip balance column
        v = clean_amount(str(cell))
        if v is not None:
            amounts.append((cell, v))

    if amounts:
        # Use keywords to decide direction
        is_debit_row = bool(re.search(
            r'\b(WITHDRAWAL|DEBIT|DR|PAID OUT|PURCHASE|CHARGE|FEE|PAYMENT)\b',
            row_text
        ))
        is_credit_row = bool(re.search(
            r'\b(DEPOSIT|CREDIT|CR|PAID IN|TRANSFER IN|DIVIDEND|SALARY|REFUND)\b',
            row_text
        ))

        # Pick the largest absolute value as the transaction amount
        _, best_val = max(amounts, key=lambda x: abs(x[1]))

        if best_val < 0:
            debit = abs(best_val)
        elif is_debit_row and not is_credit_row:
            debit = abs(best_val)
        elif is_credit_row and not is_debit_row:
            credit = abs(best_val)
        else:
            # Fallback: positive = credit
            credit = abs(best_val)

    return debit, credit


def classify_signed_amount(
    raw_amount: str,
    row_text: str = "",
) -> Tuple[Optional[float], Optional[float]]:
    """
    Classify a single signed amount value into (debit, credit).

    Rules:
      - Negative (trailing '-', leading '-', parentheses) → debit
      - Positive → credit
      - If amount is zero or unparseable → (None, None)
      - Row context keywords can override sign for edge cases.
    """
    val = clean_amount(raw_amount)
    if val is None or val == 0:
        return None, None

    if val < 0:
        return abs(val), None
    else:
        # Check row context for debit keywords on positive amounts
        upper = row_text.upper()
        if re.search(
            r'\b(WITHDRAWAL|DEBIT|DR|FEE|CHARGE|OVERDRAFT|PURCHASE|'
            r'ACH\s*(?:DEBIT|PAYMENT)|POS\s*DEB|TRANSFER\s*TO|CHECK)\b',
            upper
        ):
            return abs(val), None
        return None, abs(val)


# Statement period detection
def detect_statement_period(
    rows: List[List[str]],
) -> Tuple[Optional[int], Optional[int]]:
    """
    Scan preamble rows (first 30) for a statement date range.

    Returns (year, month) for the primary statement period, or (None, None).
    Used to resolve ambiguous short dates like "12/01" → Dec 2025 vs Dec 2026.
    """
    for row in rows[:40]:
        row_text = ' '.join(str(c) for c in row)

        # Pattern: "Beginning Balance  12/01/25" or "Date  1/30/26"
        # or "** Ending Balance  2/28/26"
        for cell in row:
            cell_str = str(cell).strip()
            # Look for a full date with 2- or 4-digit year
            m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', cell_str)
            if m:
                d1, d2, yr_raw = int(m.group(1)), int(m.group(2)), int(m.group(3))
                yr = yr_raw if yr_raw > 99 else (2000 + yr_raw if yr_raw < 70 else 1900 + yr_raw)
                # d1 is likely month (MM/DD/YY in US format)
                mo = d1 if d1 <= 12 else d2
                return yr, mo

            # Pattern: "04-2026" / "04/2026" / "2026-04" in statement headers.
            m_my = re.search(r'\b(0?[1-9]|1[0-2])[/\-](20\d{2})\b', cell_str)
            if m_my:
                return int(m_my.group(2)), int(m_my.group(1))
            m_ym = re.search(r'\b(20\d{2})[/\-](0?[1-9]|1[0-2])\b', cell_str)
            if m_ym:
                return int(m_ym.group(1)), int(m_ym.group(2))

        # Fall back to row-level scan for period tokens.
        m_my = re.search(r'\b(0?[1-9]|1[0-2])[/\-](20\d{2})\b', row_text)
        if m_my:
            return int(m_my.group(2)), int(m_my.group(1))
        m_ym = re.search(r'\b(20\d{2})[/\-](0?[1-9]|1[0-2])\b', row_text)
        if m_ym:
            return int(m_ym.group(1)), int(m_ym.group(2))

    return None, None


# Confidence scoring

def calculate_confidence(transactions: List[Dict]) -> float:
    if not transactions:
        return 0.0
    total = 0.0
    for t in transactions:
        s = 0.0
        if t.get('date'):
            s += 0.3
        if t.get('description') and len(t.get('description', '')) > 3:
            s += 0.2
        if t.get('debit') is not None or t.get('credit') is not None:
            s += 0.4
        total += s
    return round(total / len(transactions), 2)


def deduplicate_transactions(transactions: List) -> List:
    """
    Remove duplicate transaction rows produced when multiple parsers overlap
    (e.g. main table + check-detail extraction).
    """
    seen: set = set()
    unique = []

    for txn in transactions:
        if hasattr(txn, "dict"):
            data = txn.dict()
        elif isinstance(txn, dict):
            data = txn
        else:
            data = {
                "date": getattr(txn, "date", None),
                "description": getattr(txn, "description", ""),
                "debit": getattr(txn, "debit", None),
                "credit": getattr(txn, "credit", None),
            }

        debit = data.get("debit")
        credit = data.get("credit")
        key = (
            data.get("date"),
            round(float(debit), 2) if debit is not None else None,
            round(float(credit), 2) if credit is not None else None,
            (data.get("description") or "").strip().lower()[:100],
        )

        if key in seen:
            continue
        seen.add(key)
        unique.append(txn)

    return unique


def sum_transaction_totals(transactions: List) -> Dict[str, float]:
    """Sum debit and credit columns from extracted transactions."""
    total_debits = 0.0
    total_credits = 0.0
    for txn in transactions:
        debit = getattr(txn, "debit", None)
        credit = getattr(txn, "credit", None)
        if debit:
            total_debits += float(debit)
        if credit:
            total_credits += float(credit)
    return {
        "total_debits": round(total_debits, 2),
        "total_credits": round(total_credits, 2),
    }
