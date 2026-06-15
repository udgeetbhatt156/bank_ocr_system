import re
from datetime import datetime
from typing import Optional

_CURRENT_YEAR = datetime.now().year

_MONTH_MAP = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
    'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


def parse_date(
    raw_text: str,
    *,
    statement_year: Optional[int] = None,
    statement_month: Optional[int] = None,
) -> Optional[str]:
    if not raw_text or not isinstance(raw_text, str):
        return None

    s = raw_text.strip()
    if re.search(r'[/\-\.]', s) and len(s) <= 15:
        s = re.sub(r'(?<=\d)[Oo]|[Oo](?=\d)', '0', s)
        s = re.sub(r'(?<=\d)[lI]|[lI](?=\d)', '1', s)

    year_hint = statement_year or _CURRENT_YEAR

    m = re.search(r'\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b', s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date().isoformat()
        except ValueError:
            pass

    m = re.search(r'\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})\b', s)
    if m:
        d1, d2, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
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

    m = re.search(r'\b([A-Za-z]{3})[A-Za-z]*\.?\s+(\d{1,2})(?:[,\s]+(\d{4}))?\b', s)
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

    m = re.search(r'\b(\d{1,2})[/\-\.](\d{1,2})\b', s)
    if m:
        d1, d2 = int(m.group(1)), int(m.group(2))
        if d1 > 12:
            try:
                return datetime(year_hint, d2, d1).date().isoformat()
            except ValueError:
                pass
        elif d2 > 12:
            try:
                return datetime(year_hint, d1, d2).date().isoformat()
            except ValueError:
                pass
        else:
            try:
                return datetime(year_hint, d1, d2).date().isoformat()
            except ValueError:
                pass

    return None
