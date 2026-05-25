"""
Post-processing Service
Cleans amounts, dates, and classifies debit/credit transactions.

Handles real-world formats from:
  - BMO Bank       : "Jul 01", "$1,234.56", "-$700.00"
  - Suncoast CU    : "04/01/2025", signed amounts
  - US Bank        : "10/02", plain numbers
  - HDFC/ICICI     : "01/01/2024", "₹1,234.56"
  - YES Bank       : "10/11/2018", colored amounts
  - Bank of Baroda : "24-04-2023"
  - First Bank Wiki: "2003-10-08"
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


# Amount cleaning 

def clean_amount(raw_value: str) -> Optional[float]:
    """
    Parse an amount string into a float.

    Handles:
      $1,234.56  -$700.00  ₹1,234.56  1,234.56 Dr  1234.56 Cr
      (1,234.56)  +1234    1.234,56 (European)
    Returns the absolute value (sign is handled by classify_debit_credit).
    """
    if not raw_value or not isinstance(raw_value, str):
        return None

    s = raw_value.strip()

    # Parentheses → negative  e.g. (1,234.56)
    is_paren_negative = s.startswith('(') and s.endswith(')')
    if is_paren_negative:
        s = s[1:-1]

    # Strip currency symbols and common prefixes
    s = re.sub(r'Rs\.?|INR', '', s, flags=re.IGNORECASE)
    s = re.sub(r'[$₹€£¥]', '', s)

    # Strip Dr / Cr suffixes
    s = re.sub(r'\s*(Dr|Cr|DR|CR)\.?$', '', s, flags=re.IGNORECASE)

    # Remove spaces
    s = s.strip()

    # Handle leading minus/plus
    negative = s.startswith('-')
    s = s.lstrip('+-').strip()

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

def parse_date(raw_text: str) -> Optional[str]:
    """
    Parse a date string into ISO format (YYYY-MM-DD).

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
        r'\b([A-Za-z]{3})\s+(\d{1,2})(?:[,\s]+(\d{4}))?\b', s
    )
    if m:
        mon_str = m.group(1).lower()
        if mon_str in _MONTH_MAP:
            mo = _MONTH_MAP[mon_str]
            dy = int(m.group(2))
            yr = int(m.group(3)) if m.group(3) else _CURRENT_YEAR
            try:
                return datetime(yr, mo, dy).date().isoformat()
            except ValueError:
                pass

    # 5. "15-Jan-24" or "15-Jan-2024"  (DD-Mon-YY)
    m = re.search(r'\b(\d{1,2})-([A-Za-z]{3})-(\d{2,4})\b', s)
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
    m = re.search(r'\b(\d{1,2})/(\d{1,2})\b', s)
    if m:
        d1, d2 = int(m.group(1)), int(m.group(2))
        yr = _CURRENT_YEAR
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
) -> Tuple[Optional[float], Optional[float]]:
    """
    Return (debit, credit) amounts from a data row.

    Handles:
      1. Separate Withdrawal / Deposit columns  (BMO, Suncoast, US Bank)
      2. Single signed Amount column            (Suncoast savings: -5000 / +10000)
      3. Separate Debit / Credit columns        (HDFC, ICICI, YES Bank)
      4. Single Amount with Dr/Cr keyword       (Bank of Baroda)
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
        if val is not None:
            if val < 0:
                debit = abs(val)
            else:
                credit = val
        return debit, credit

    # Format 3: scan all cells for signed amounts
    row_text = ' '.join(str(c) for c in row).upper()
    amounts = []
    for cell in row:
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
        if t.get('reference'):
            s += 0.1
        total += s
    return round(total / len(transactions), 2)
