import re
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

# DATE_PATTERNS = [
#     r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
#     r"\b\d{4}[./-]\d{1,2}[./-]\d{1,2}\b",
# ]
# DATE_REGEX = re.compile("|".join(DATE_PATTERNS))
# AMOUNT_REGEX = re.compile(r"[₹Rs]*\s*[-+]?[\d,]+(?:\.\d{1,2})?")
# REFERENCE_REGEX = re.compile(r"\b(?:UTR|REF|Ref|CHQ|Cheque|Cheque No|Txn)[:#\s]*([A-Za-z0-9-]+)", re.IGNORECASE)
# CREDIT_WORDS = re.compile(r"\b(CR|CR\.|CREDIT|CREDITED|CREDITED TO)\b", re.IGNORECASE)
# DEBIT_WORDS = re.compile(r"\b(DR|DR\.|DEBIT|DEBITED|WITHDRAWAL)\b", re.IGNORECASE)

DATE_PATTERNS = [
    r"\b(0[1-9]|1[0-2])[-/](0[1-9]|[12][0-9]|3[01])[-/](\d{2,4})\b",  # MM/DD/YYYY
    r"\b\d{2}[-/]\d{2}[-/]\d{2,4}\b",
]
DATE_REGEX = re.compile("|".join(DATE_PATTERNS))

AMOUNT_REGEX = re.compile(r'[-]?[\d,]+\.\d{2}')   # e.g., 1,535.52 or -36.00
DESCRIPTION_REGEX = re.compile(r'(?<=^\d{2}/\d{2}).*?(?=\s*[\d,]+\.\d{2})', re.MULTILINE)
TRANSACTION_LINE_REGEX = re.compile(
    r'(\d{2}/\d{2})\s+'                  # Date (MM/DD)
    r'(.+?)'                             # Description (non-greedy)
    r'\s+'                               # Space
    r'([\d,]+\.\d{2})',                  # Amount
    re.MULTILINE | re.IGNORECASE
)
CREDIT_KEYWORDS = re.compile(r'\b(CREDIT|DEPOSIT|CASH DEPOSIT|TRANSFER FROM|REFUND|ACH CREDIT)\b', re.IGNORECASE)
DEBIT_KEYWORDS = re.compile(r'\b(DEBIT|WITHDRAWAL|TRANSFER TO|ACH DEBIT|CARD PURCHASE|OVERDRAFT FEE|RETURNED ITEM|WIRE)\b', re.IGNORECASE)
def normalize_amount(raw_value: str) -> Optional[Decimal]:
    if not raw_value:
        return None
    cleaned = raw_value.replace("₹", "").replace("Rs", "").replace(",", "").strip()
    cleaned = re.sub(r"[^0-9.\-+]", "", cleaned)
    if not cleaned or cleaned in {"-", "+"}:
        return None
    try:
        return Decimal(cleaned)
    except Exception:
        return None


def parse_date(raw_text: str) -> Optional[str]:
    match = DATE_REGEX.search(raw_text)
    if not match:
        return None
    raw_value = match.group(0)
    formats = ["%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%Y.%m.%d"]
    for fmt in formats:
        try:
            parsed = datetime.strptime(raw_value, fmt)
            return parsed.date().isoformat()
        except ValueError:
            continue
    return raw_value


def split_columns(raw_line: str) -> List[str]:
    return [segment.strip() for segment in re.split(r"\s{2,}", raw_line) if segment.strip()]


def find_amounts(raw_text: str) -> List[Decimal]:
    values = []
    for match in AMOUNT_REGEX.findall(raw_text):
        amount = normalize_amount(match)
        if amount is not None:
            values.append(amount) 
    return values


@dataclass
class TransactionRecord:
    date: Optional[str]
    description: str
    debit: Optional[Decimal]
    credit: Optional[Decimal]
    balance: Optional[Decimal]


def build_transaction(raw_line: str) -> Optional[TransactionRecord]:
    date = parse_date(raw_line)
    if not date:
        return None

    columns = split_columns(raw_line)
    description = raw_line
    amounts = find_amounts(raw_line)
    debit = None
    credit = None
    balance = None

    if columns and DATE_REGEX.search(columns[0]):
        description = " ".join(columns[1:-2]) if len(columns) > 3 else " ".join(columns[1:])
        line_tail = " ".join(columns[-2:]) if len(columns) > 2 else raw_line
        amounts = find_amounts(line_tail) or amounts

    if CREDIT_WORDS.search(raw_line):
        if amounts:
            credit = amounts[0]
            balance = amounts[1] if len(amounts) > 1 else None
    elif DEBIT_WORDS.search(raw_line):
        if amounts:
            debit = amounts[0]
            balance = amounts[1] if len(amounts) > 1 else None
    else:
        if len(amounts) == 1:
            debit = amounts[0]
        elif len(amounts) == 2:
            debit = amounts[0]
            balance = amounts[1]
        elif len(amounts) >= 3:
            debit = amounts[0]
            credit = amounts[1]
            balance = amounts[2]

    if not description or description == date:
        description = raw_line

    return TransactionRecord(
        date=date,
        description=description.strip(),
        debit=debit,
        credit=credit,
        balance=balance,
    )


def extract_transactions(raw_text: str) -> List[dict]:
    raw_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    transactions = []
    for raw_line in raw_lines:
        transaction = build_transaction(raw_line)
        if transaction:
            transactions.append(asdict(transaction))
    return transactions
