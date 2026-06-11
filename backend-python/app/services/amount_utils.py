import re
from typing import Optional

_OCR_DIGIT_FIXES = str.maketrans({
    'O': '0', 'o': '0',
    'l': '1', 'I': '1', 'i': '1',
    'S': '5', 's': '5',
    'B': '8',
    'G': '6', 'g': '6',
    'Z': '2', 'z': '2',
    'T': '7',
})


def clean_amount(raw_value: str) -> Optional[float]:
    if not raw_value or not isinstance(raw_value, str):
        return None

    s = raw_value.strip()
    is_paren_negative = s.startswith('(') and s.endswith(')')
    if is_paren_negative:
        s = s[1:-1]

    s = re.sub(r'Rs\.?|INR', '', s, flags=re.IGNORECASE)
    s = re.sub(r'[$₹€£¥]', '', s)
    s = re.sub(r'\s*(Dr|Cr|DR|CR)\.?$', '', s, flags=re.IGNORECASE)
    s = s.strip().strip('*#').strip()

    if re.search(r'(?:x{2,}|\*{2,})\d{3,}', s, flags=re.IGNORECASE):
        return None

    if re.search(r'\d', s) and len(s) <= 20:
        corrected = []
        for i, ch in enumerate(s):
            if ch in _OCR_DIGIT_FIXES and ch.isalpha():
                prev_ok = (i == 0) or s[i - 1].isdigit() or s[i - 1] in '.,- '
                next_ok = (i == len(s) - 1) or s[i + 1].isdigit() or s[i + 1] in '.,- '
                if prev_ok and next_ok:
                    corrected.append(chr(_OCR_DIGIT_FIXES[ord(ch)]))
                else:
                    corrected.append(ch)
            else:
                corrected.append(ch)
        s = ''.join(corrected)

    if re.search(r'[A-Za-z/]', s):
        return None

    digits_only = re.sub(r'[^0-9]', '', s)
    if len(digits_only) > 12:
        return None

    negative = s.startswith('-') or s.endswith('-')
    s = s.strip('+-').strip()

    if re.search(r'\d,\d{3}[,\d]', s):
        s = s.replace(',', '')
    elif re.search(r'\d\.\d{3},\d{2}$', s):
        s = s.replace('.', '').replace(',', '.')
    else:
        s = s.replace(',', '')

    s = re.sub(r'[^\d.]', '', s)
    if not s or s == '.':
        return None

    try:
        val = float(s)
        if is_paren_negative or negative:
            val = -val
        return val
    except ValueError:
        return None

def clean_psb_amount(raw_value: str) -> Optional[float]:
    """
    Clean PeoplesSouth Bank amounts, handling the `-SC` suffix for Service Charges.
    """
    if not raw_value or not isinstance(raw_value, str):
        return None
    
    s = raw_value.strip()
    
    # Handle the "22.55-SC" service charge marker
    if s.endswith("-SC") or s.endswith("-sc"):
        s = s[:-3] + "-" # Replace "-SC" with just "-" to trigger negative logic
        
    return clean_amount(s)
