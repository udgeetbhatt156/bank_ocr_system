"""SoFi Bank parser."""

import re
from typing import List, Optional, Tuple

from app.models.schemas import Transaction
from app.parsers.base import BaseParser
from app.parsers.result import ParseResult, StatementMetadata
from app.parsers.registry import register_parser, register_template_parser
from app.services.amount_utils import clean_amount
from app.services.date_utils import parse_date
from app.services.metadata_extractor import extract_statement_metadata
from app.services.postprocessor import calculate_confidence


_SOFI_SINGLE_LINE_RE = re.compile(
    r"^"
    r"(?P<date>"
    r"(?:[A-Za-z]{3}\s+\d{1,2}(?:,?\s+\d{4})?)"
    r"|(?:\d{1,2}/\d{1,2}(?:/\d{2,4})?)"
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


class SofiParser(BaseParser):
    """Parser for SoFi signed amount with TYPE-column statements."""

    parser_id = "sofi_signed_type"

    def extract_metadata(self) -> StatementMetadata:
        transactions = self.extract_transactions()
        metadata = extract_statement_metadata(self.context.rows, transactions)
        return StatementMetadata(
            bank_id=self.context.bank_id or "SOFI",
            bank_name=metadata.get("bank_name") or "SoFi Bank",
            account_number=metadata.get("account_number"),
            customer_name=metadata.get("customer_name"),
            current_balance=metadata.get("current_balance"),
        )

    def extract_transactions(self) -> List[Transaction]:
        return self._parse_sofi_signed_type_rows(
            self.context.rows,
            statement_year=self.context.statement_year,
        )

    def parse(self) -> ParseResult:
        transactions = self.extract_transactions()
        metadata = extract_statement_metadata(self.context.rows, transactions)
        normalized_metadata = StatementMetadata(
            bank_id=self.context.bank_id or "SOFI",
            bank_name=metadata.get("bank_name") or "SoFi Bank",
            account_number=metadata.get("account_number"),
            customer_name=metadata.get("customer_name"),
            current_balance=metadata.get("current_balance"),
        )
        return ParseResult(
            metadata=normalized_metadata,
            transactions=transactions,
            confidence=calculate_confidence([txn.dict() for txn in transactions]),
            parser_id=self.parser_id,
            bank_id=normalized_metadata.bank_id,
            template_id=self.context.template_id,
        )

    def _parse_sofi_amount_balance(
        self,
        raw: str,
    ) -> Tuple[Optional[float], Optional[float]]:
        raw = raw.strip()
        m = re.match(r"([+-]\$?[\d,]+\.?\d*)\s+\$?([\d,]+\.?\d*)", raw)
        if m:
            amount = clean_amount(m.group(1))
            balance = clean_amount(m.group(2))
            if balance is not None:
                balance = abs(balance)
            return amount, balance

        amount = clean_amount(raw)
        return amount, None

    def _parse_sofi_signed_type_rows(
        self,
        rows: List[List[str]],
        *,
        statement_year: Optional[int] = None,
    ) -> List[Transaction]:
        transactions: List[Transaction] = []
        in_transaction_table = False

        for row in rows:
            if not row or not any(str(c).strip() for c in row):
                continue

            row_text = " ".join(str(c) for c in row).strip()
            row_lower = row_text.lower()

            if "date" in row_lower and "type" in row_lower and "amount" in row_lower:
                in_transaction_table = True
                continue

            if _SOFI_TRANSACTION_ID_RE.match(row_text):
                continue

            if _SOFI_SKIP_RE.search(row_text):
                if "date" in row_lower and "type" in row_lower and "amount" in row_lower:
                    in_transaction_table = True
                continue

            if not in_transaction_table:
                continue

            if len(row) >= 3:
                date_str = parse_date(str(row[0]).strip(), statement_year=statement_year)
                if date_str:
                    txn_type = str(row[1]).strip() if len(row) > 1 else ""
                    description = str(row[2]).strip() if len(row) > 2 else ""

                    if txn_type and description:
                        full_desc = f"{txn_type} {description}"
                    elif txn_type:
                        full_desc = txn_type
                    else:
                        full_desc = description or row_text

                    amount_val: Optional[float] = None
                    balance: Optional[float] = None

                    if len(row) >= 5:
                        amount_val = clean_amount(str(row[3]))
                        balance = clean_amount(str(row[4]))
                        if balance is not None:
                            balance = abs(balance)
                    elif len(row) >= 4:
                        amount_val, balance = self._parse_sofi_amount_balance(str(row[3]))
                    else:
                        for cell in row[2:]:
                            amount_val, balance = self._parse_sofi_amount_balance(str(cell))
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

            if len(row) == 1:
                line = str(row[0]).strip()
                line_clean = re.sub(
                    r"\s+Transaction\s+ID:\s*\S+\s*$", "", line, flags=re.IGNORECASE
                )

                match = _SOFI_SINGLE_LINE_RE.match(line)
                if match:
                    date_str = parse_date(
                        match.group("date").strip(), statement_year=statement_year
                    )
                    if date_str:
                        txn_type = match.group("type").strip()
                        description = match.group("desc").strip()
                        full_desc = f"{txn_type} {description}"

                        amount_val = clean_amount(match.group("amount"))
                        balance = clean_amount(match.group("balance"))
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

                if not re.search(r"\d{1,2}[/\-]\d{1,2}", line_clean) and not re.search(
                    r"[A-Za-z]{3}\s+\d{1,2}", line_clean
                ):
                    continue

                date_str = None
                leftover = line_clean
                date_match = re.match(
                    r"([A-Za-z]{3}\s+\d{1,2}(?:,?\s+\d{4})?)\s+(.*)", line_clean
                )
                if date_match:
                    date_str = parse_date(
                        date_match.group(1).strip(), statement_year=statement_year
                    )
                    leftover = date_match.group(2).strip()
                if not date_str:
                    date_match = re.match(
                        r"(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s+(.*)", line_clean
                    )
                    if date_match:
                        date_str = parse_date(
                            date_match.group(1).strip(), statement_year=statement_year
                        )
                        leftover = date_match.group(2).strip()

                if not date_str:
                    continue

                amount_matches = list(re.finditer(r"[+-]?\$?[\d,]+\.\d{2}", leftover))
                if not amount_matches:
                    continue

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

                description = leftover[:desc_end].strip() or leftover

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


register_parser("SOFI", SofiParser)
register_template_parser("sofi_digital_activity_v1", SofiParser)
