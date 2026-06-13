"""Washington Trust Bank parser."""

import re
from typing import Any, Dict, List, Optional, Tuple

from app.models.schemas import Transaction
from app.parsers.base import BaseParser
from app.parsers.registry import register_parser, register_template_parser
from app.parsers.result import ParseResult, StatementMetadata
from app.services.amount_utils import clean_amount
from app.services.date_utils import parse_date
from app.services.postprocessor import calculate_confidence


_BANK_ID = "WASHINGTON_TRUST_BANK"
_BANK_NAME = "Washington Trust Bank"
_TEMPLATE_ID = "washington_trust_bank_v1"

_DATE_START_RE = re.compile(r"^\s*(?P<date>\d{1,2}/\d{1,2})(?!/)\b\s*(?P<rest>.*)$")
_MONEY_RE = re.compile(r"\$?\s*\(?\d[\d,]*\.\d{2}\)?")
_CHECK_RE = re.compile(
    r"\b(?P<check>\d{3,})\s+(?P<date>\d{1,2}/\d{2})\s+\$?\s*(?P<amount>\d[\d,]*\.\d{2})\b"
)
_CHECK_DATE_FIRST_RE = re.compile(
    r"\b(?P<date>\d{1,2}/\d{2})\s+(?P<check>\d{3,})\s+\$?\s*(?P<amount>\d[\d,]*\.\d{2})\b"
)
_DAILY_BALANCE_PAIR_RE = re.compile(
    r"\b(?P<date>\d{1,2}/\d{2})\s+\$?\s*(?P<balance>\d[\d,]*\.\d{2})\b"
)


class WashingtonTrustBankParser(BaseParser):
    """Parser for Washington Trust Bank activity/date-order statements."""

    parser_id = _TEMPLATE_ID

    def extract_metadata(self) -> StatementMetadata:
        return self._extract_metadata()

    def extract_transactions(self) -> List[Transaction]:
        transactions, _ = self._extract_activity_transactions()
        return self._sort_transactions([*transactions, *self._checks_as_transactions()])

    def parse(self) -> ParseResult:
        metadata = self._extract_metadata()
        activity_transactions, structured_activity_transactions = self._extract_activity_transactions()
        checks_register = self._extract_checks_register()
        check_transactions = self._checks_as_transactions(checks_register)
        transactions = self._sort_transactions([*activity_transactions, *check_transactions])
        structured_transactions = self._sort_structured_transactions([
            *structured_activity_transactions,
            *self._structured_check_transactions(checks_register),
        ])
        daily_balances = self._extract_daily_balances()
        validation_errors = self._validate(metadata, transactions)

        structured_output = {
            "bank_name": metadata.bank_name,
            "account_holder": {
                "name": metadata.customer_name,
                "address": metadata.customer_address,
            },
            "account_type": metadata.account_type,
            "account_number": metadata.account_number,
            "statement_period": {
                "start_date": self._format_output_date(metadata.statement_start_date),
                "end_date": self._format_output_date(metadata.statement_end_date),
            },
            "summary_financials": {
                "beginning_balance": metadata.opening_balance,
                "ending_balance": metadata.closing_balance,
                "total_credits": metadata.total_credits,
                "total_debits": metadata.total_debits,
            },
            "transactions": structured_transactions,
            "checks_posted": checks_register,
            "daily_balance_table": daily_balances,
        }
        if validation_errors:
            structured_output["validation_errors"] = validation_errors

        return ParseResult(
            metadata=metadata,
            transactions=transactions,
            confidence=calculate_confidence([txn.dict() for txn in transactions]),
            parser_id=self.parser_id,
            bank_id=_BANK_ID,
            template_id=self.context.template_id or _TEMPLATE_ID,
            checks_register=checks_register,
            validation_errors=validation_errors,
            extra={"washington_trust_output": structured_output},
        )

    def _extract_metadata(self) -> StatementMetadata:
        text = self._text()
        lines = self._lines()
        period_start, period_end = self._extract_period(text)
        customer_name, customer_address = self._extract_customer_block(lines)
        account_type, account_number = self._extract_account_details(text, lines)

        return StatementMetadata(
            bank_id=self.context.bank_id or _BANK_ID,
            bank_name=_BANK_NAME,
            account_number=account_number,
            account_holder=customer_name,
            customer_name=customer_name,
            customer_address=customer_address,
            account_type=account_type,
            statement_start_date=period_start,
            statement_end_date=period_end,
            opening_balance=self._extract_labeled_amount(
                text,
                ["Beginning Balance", "Previous Balance", "Starting Balance"],
            ),
            closing_balance=self._extract_labeled_amount(
                text,
                ["Ending Balance", "Current Balance", "Closing Balance"],
            ),
            current_balance=self._extract_labeled_amount(
                text,
                ["Ending Balance", "Current Balance", "Closing Balance"],
            ),
            total_credits=self._extract_labeled_amount(
                text,
                ["Deposits/Credits", "Total Additions", "Total Credits"],
            ),
            total_debits=self._extract_labeled_amount(
                text,
                ["Checks/Debits", "Total Subtractions", "Total Debits"],
            ),
        )

    def _extract_activity_transactions(self) -> Tuple[List[Transaction], List[Dict[str, Any]]]:
        debug_result = self._extract_activity_transactions_from_debug()
        if debug_result[0]:
            return debug_result

        groups = self._group_activity_rows(self._activity_rows())
        transactions: List[Transaction] = []
        structured: List[Dict[str, Any]] = []

        for group in groups:
            parsed = self._parse_activity_group(group)
            if parsed is None:
                continue
            transaction, output = parsed
            transactions.append(transaction)
            output["seq"] = len(structured) + 1
            structured.append(output)

        return transactions, structured

    def _extract_activity_transactions_from_debug(self) -> Tuple[List[Transaction], List[Dict[str, Any]]]:
        groups = self._debug_activity_groups()
        transactions: List[Transaction] = []
        structured: List[Dict[str, Any]] = []

        for group in groups:
            parsed = self._parse_debug_activity_group(group)
            if parsed is None:
                continue
            transaction, output = parsed
            transactions.append(transaction)
            output["seq"] = len(structured) + 1
            structured.append(output)

        return transactions, structured

    def _debug_activity_groups(self) -> List[Dict[str, Any]]:
        groups: List[Dict[str, Any]] = []
        for page in self.context.debug_extraction.get("pages", []):
            in_activity = False
            add_x: Optional[float] = None
            sub_x: Optional[float] = None
            current: Optional[Dict[str, Any]] = None

            for row in page.get("rows", []):
                text = str(row.get("text") or "").strip()
                lower = text.lower()
                if not text:
                    continue
                if re.search(r"activity\s+in\s+date\s+order", lower):
                    in_activity = True
                    current = None
                    continue
                if not in_activity:
                    continue
                if re.search(
                    r"(checks?\s+posted|checks?\s+in\s+number\s+order|daily\s+balance\s+information|balance\s+this\s+statement)",
                    lower,
                ):
                    if current:
                        groups.append(current)
                        current = None
                    in_activity = False
                    continue
                if self._is_debug_header(row):
                    add_x, sub_x = self._debug_header_amount_x(row)
                    continue
                if self._is_metadata_line(text) or self._is_header_or_noise([text]):
                    continue

                date_match = _DATE_START_RE.match(text)
                if date_match:
                    if current:
                        groups.append(current)
                    current = {
                        "date": date_match.group("date"),
                        "rows": [row],
                        "add_x": add_x,
                        "sub_x": sub_x,
                    }
                elif current:
                    current["rows"].append(row)

            if current:
                groups.append(current)

        return groups

    def _parse_debug_activity_group(
        self,
        group: Dict[str, Any],
    ) -> Optional[Tuple[Transaction, Dict[str, Any]]]:
        rows = group.get("rows") or []
        if not rows:
            return None

        amount_match = self._debug_amount_cell(rows[0])
        if not amount_match:
            return None
        amount, amount_x = amount_match

        add_x = group.get("add_x")
        sub_x = group.get("sub_x")
        if add_x is not None and sub_x is not None:
            if abs(amount_x - float(sub_x)) < abs(amount_x - float(add_x)):
                credit, debit = None, abs(amount)
            else:
                credit, debit = abs(amount), None
        else:
            credit, debit = self._classify_amount(abs(amount), " ".join(str(r.get("text") or "") for r in rows))

        row_texts = [str(row.get("text") or "").strip() for row in rows]
        source_text = " ".join(text for text in row_texts if text)
        description = self._description_from_debug_rows(rows)
        if not description:
            return None

        date_iso = self._parse_statement_date(str(group.get("date") or ""))
        transaction = Transaction(
            date=date_iso,
            description=description,
            debit=debit,
            credit=credit,
            balance=None,
        )
        output = {
            "date": self._format_output_date(date_iso),
            "description": description,
            "credit": credit,
            "debit": debit,
            "running_balance": None,
            "source_text": source_text,
        }
        return transaction, output

    def _is_debug_header(self, row: Dict[str, Any]) -> bool:
        text = str(row.get("text") or "").lower()
        return "date" in text and "description" in text and (
            "additions" in text or "subtractions" in text
        )

    def _debug_header_amount_x(self, row: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
        add_x: Optional[float] = None
        sub_x: Optional[float] = None
        for cell in row.get("cells", []):
            text = str(cell.get("text") or "").lower()
            x = self._cell_center_x(cell)
            if x is None:
                continue
            if "addition" in text:
                add_x = x
            elif "subtraction" in text:
                sub_x = x
        return add_x, sub_x

    def _debug_amount_cell(self, row: Dict[str, Any]) -> Optional[Tuple[float, float]]:
        matches: List[Tuple[float, float]] = []
        for cell in row.get("cells", []):
            text = str(cell.get("text") or "")
            amount_matches = list(_MONEY_RE.finditer(text))
            if not amount_matches:
                continue
            amount = clean_amount(amount_matches[-1].group())
            x = self._cell_center_x(cell)
            if amount is not None and x is not None:
                matches.append((abs(amount), x))
        if not matches:
            return None
        return matches[-1]

    def _description_from_debug_rows(self, rows: List[Dict[str, Any]]) -> str:
        parts: List[str] = []
        for row in rows:
            text = str(row.get("text") or "").strip()
            if not text or self._is_metadata_line(text):
                continue
            text = _DATE_START_RE.sub(lambda m: m.group("rest"), text).strip()
            cleaned = self._remove_amounts(text)
            if cleaned:
                parts.append(cleaned.replace("|", " "))
        return re.sub(r"\s+", " ", " ".join(parts)).strip()

    def _cell_center_x(self, cell: Dict[str, Any]) -> Optional[float]:
        x0 = cell.get("x0")
        x1 = cell.get("x1")
        if x0 is not None and x1 is not None:
            return (float(x0) + float(x1)) / 2
        return None

    def _parse_activity_group(
        self,
        group: List[List[str]],
    ) -> Optional[Tuple[Transaction, Dict[str, Any]]]:
        date_text, first_description = self._split_date_from_row(group[0])
        if not date_text:
            return None

        credit, debit = self._extract_addition_subtraction(group)
        if credit is None and debit is None:
            return None

        description = self._extract_description(group, first_description)
        if not description:
            return None

        date_iso = self._parse_statement_date(date_text)
        source_text = " ".join(self._row_text(row) for row in group if self._row_text(row))
        transaction = Transaction(
            date=date_iso,
            description=description,
            debit=debit,
            credit=credit,
            balance=None,
        )
        output = {
            "date": self._format_output_date(date_iso),
            "description": description,
            "credit": credit,
            "debit": debit,
            "running_balance": None,
            "source_text": source_text,
        }
        return transaction, output

    def _group_activity_rows(self, rows: List[List[str]]) -> List[List[List[str]]]:
        groups: List[List[List[str]]] = []
        current: List[List[str]] = []

        for row in rows:
            if not row or self._is_header_or_noise(row) or self._is_metadata_line(self._row_text(row)):
                continue
            if self._row_has_start_date(row):
                if current:
                    groups.append(current)
                current = [row]
            elif current:
                current.append(row)

        if current:
            groups.append(current)
        return groups

    def _extract_addition_subtraction(
        self,
        group: List[List[str]],
    ) -> Tuple[Optional[float], Optional[float]]:
        first = [str(cell).strip() for cell in group[0]]
        if len(first) >= 4:
            credit = clean_amount(first[-2])
            debit = clean_amount(first[-1])
            if credit is not None:
                return abs(credit), None
            if debit is not None:
                return self._classify_amount(abs(debit), " ".join(self._row_text(row) for row in group))

        text = " ".join(self._row_text(row) for row in group)
        matches = list(_MONEY_RE.finditer(text))
        if not matches:
            return None, None
        amount = clean_amount(matches[-1].group())
        if amount is None:
            return None, None

        return self._classify_amount(abs(amount), text)

    def _extract_description(self, group: List[List[str]], first_description: str) -> str:
        parts: List[str] = []
        if first_description:
            parts.append(self._remove_amounts(first_description))
        for row in group[1:]:
            text = self._row_text(row)
            if text:
                parts.append(self._remove_amounts(text))
        return re.sub(r"\s+", " ", " ".join(part for part in parts if part)).strip()

    def _extract_checks_register(self) -> List[Dict[str, Any]]:
        checks: List[Dict[str, Any]] = []
        seen = set()
        lines = self._section_lines(
            r"checks?\s+(?:posted|in\s+number\s+order)",
            [r"daily\s+balance", r"activity\s+in\s+date\s+order", r"summary"],
        )
        for line in lines:
            for pattern in (_CHECK_RE, _CHECK_DATE_FIRST_RE):
                for match in pattern.finditer(line):
                    amount = clean_amount(match.group("amount"))
                    date_iso = self._parse_statement_date(match.group("date"))
                    if amount is None or not date_iso:
                        continue
                    key = (match.group("check"), date_iso, round(abs(amount), 2))
                    if key in seen:
                        continue
                    seen.add(key)
                    checks.append({
                        "check_number": match.group("check"),
                        "date": self._format_output_date(date_iso),
                        "amount": abs(amount),
                    })
        return checks

    def _checks_as_transactions(
        self,
        checks: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Transaction]:
        check_rows = checks if checks is not None else self._extract_checks_register()
        transactions: List[Transaction] = []
        for check in check_rows:
            transactions.append(Transaction(
                date=self._parse_output_date(check.get("date")),
                description=f"Check {check.get('check_number')}",
                debit=check.get("amount"),
                credit=None,
                balance=None,
            ))
        return transactions

    def _structured_check_transactions(
        self,
        checks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for check in checks:
            rows.append({
                "date": check.get("date"),
                "description": f"Check {check.get('check_number')}",
                "credit": None,
                "debit": check.get("amount"),
                "running_balance": None,
                "check_number": check.get("check_number"),
                "source_text": f"Check {check.get('check_number')} {check.get('date')} {check.get('amount')}",
            })
        return rows

    def _extract_daily_balances(self) -> List[Dict[str, Any]]:
        balances: List[Dict[str, Any]] = []
        seen = set()
        lines = self._section_lines(
            r"daily\s+balance\s+information",
            [
                r"activity\s+in\s+date\s+order",
                r"checks?\s+(?:posted|in\s+number\s+order)",
                r"summary",
                r"member\s+fdic",
            ],
        )
        for line in lines:
            for match in _DAILY_BALANCE_PAIR_RE.finditer(line):
                date_iso = self._parse_statement_date(match.group("date"))
                amount = clean_amount(match.group("balance"))
                if not date_iso or amount is None:
                    continue
                key = (date_iso, round(abs(amount), 2))
                if key in seen:
                    continue
                seen.add(key)
                balances.append({
                    "date": self._format_output_date(date_iso),
                    "balance": abs(amount),
                })
        return balances

    def _validate(
        self,
        metadata: StatementMetadata,
        transactions: List[Transaction],
    ) -> List[str]:
        errors: List[str] = []
        credit_sum = round(sum(float(txn.credit or 0) for txn in transactions), 2)
        debit_sum = round(sum(float(txn.debit or 0) for txn in transactions), 2)

        if metadata.total_credits is not None and abs(credit_sum - metadata.total_credits) > 0.05:
            errors.append(
                f"Credit total mismatch: transactions={credit_sum}, statement={metadata.total_credits}."
            )
        if metadata.total_debits is not None and abs(debit_sum - metadata.total_debits) > 0.05:
            errors.append(
                f"Debit total mismatch: transactions={debit_sum}, statement={metadata.total_debits}."
            )
        if metadata.opening_balance is not None and metadata.closing_balance is not None:
            expected = round(metadata.opening_balance + credit_sum - debit_sum, 2)
            if abs(expected - metadata.closing_balance) > 0.05:
                errors.append(
                    "Balance chain failed: "
                    f"{metadata.opening_balance} + {credit_sum} - {debit_sum} "
                    f"= {expected}, expected {metadata.closing_balance}."
                )
        return errors

    def _activity_rows(self) -> List[List[str]]:
        rows = self.context.rows or [[line] for line in self._lines()]
        start: Optional[int] = None
        end = len(rows)
        for idx, row in enumerate(rows):
            if re.search(r"activity\s+in\s+date\s+order", self._row_text(row), re.IGNORECASE):
                start = idx + 1
                break
        if start is None:
            return []
        for idx in range(start, len(rows)):
            if re.search(
                r"(daily\s+balance\s+information|checks?\s+(posted|in\s+number\s+order)|account\s+summary|summary\s+information)",
                self._row_text(rows[idx]),
                re.IGNORECASE,
            ):
                end = idx
                break
        return rows[start:end]

    def _section_lines(self, start_pattern: str, stop_patterns: List[str]) -> List[str]:
        lines = self._lines()
        start: Optional[int] = None
        for idx, line in enumerate(lines):
            if re.search(start_pattern, line, re.IGNORECASE):
                start = idx + 1
                break
        if start is None:
            return []

        output: List[str] = []
        for line in lines[start:]:
            if any(re.search(pattern, line, re.IGNORECASE) for pattern in stop_patterns):
                break
            output.append(line)
        return output

    def _extract_period(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        patterns = [
            r"Statement\s+Period\s+(\d{1,2}/\d{1,2}/\d{2,4})\s*(?:-|to|thru|through)\s*(\d{1,2}/\d{1,2}/\d{2,4})",
            r"Statement\s+Dates?\s+(\d{1,2}/\d{1,2}/\d{2,4})\s*(?:-|to|thru|through)\s*(\d{1,2}/\d{1,2}/\d{2,4})",
            r"Period\s+Covered\s+(\d{1,2}/\d{1,2}/\d{2,4})\s*(?:-|to|thru|through)\s*(\d{1,2}/\d{1,2}/\d{2,4})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return (
                    self._parse_statement_date(match.group(1)),
                    self._parse_statement_date(match.group(2)),
                )
        return None, None

    def _extract_customer_block(self, lines: List[str]) -> Tuple[Optional[str], Optional[str]]:
        filtered: List[str] = []
        for line in lines[:60]:
            clean = line.strip()
            if not clean or self._is_metadata_line(clean):
                continue
            if re.search(r"p\.?\s*o\.?\s+box\s+2127|800\)\s*788|watrust\.com", clean, re.IGNORECASE):
                continue
            if re.search(r"\b(you\s*tube|youtube|tube|tobe)\b", clean, re.IGNORECASE):
                continue
            filtered.append(clean)

        for idx, line in enumerate(filtered):
            if re.search(r"[A-Z][A-Z0-9 &'.,-]{2,}", line) and not re.search(r"\d+\.\d{2}", line):
                address_parts = [
                    candidate
                    for candidate in filtered[idx + 1:idx + 5]
                    if self._looks_like_address(candidate)
                ]
                return line, " ".join(address_parts) or None
        return None, None

    def _extract_account_details(
        self,
        text: str,
        lines: List[str],
    ) -> Tuple[Optional[str], Optional[str]]:
        account_number: Optional[str] = None
        number_match = re.search(
            r"Account\s*(?:Number|No\.?|#)\s*:?\s*([*Xx\d-]{4,})",
            text,
            re.IGNORECASE,
        )
        if number_match:
            account_number = number_match.group(1)

        account_type: Optional[str] = None
        for line in lines[:80]:
            match = re.search(
                r"\b((?:Business\s+)?(?:Interest\s+)?(?:Checking|Savings|Money\s+Market|Analysis\s+Checking)[A-Za-z ]*)\b",
                line,
                re.IGNORECASE,
            )
            if match:
                account_type = re.sub(r"\s+", " ", match.group(1)).strip()
                break

        return account_type, account_number

    def _extract_labeled_amount(self, text: str, labels: List[str]) -> Optional[float]:
        for line in self._lines():
            for label in labels:
                if re.search(re.escape(label), line, re.IGNORECASE):
                    match = _MONEY_RE.search(line)
                    if match:
                        amount = clean_amount(match.group())
                        if amount is not None:
                            return abs(amount)
        for label in labels:
            match = re.search(
                rf"{re.escape(label)}[^\d$()\-]{{0,40}}(\(?\$?\s*\d[\d,]*\.\d{{2}}\)?)",
                text,
                re.IGNORECASE,
            )
            if match:
                amount = clean_amount(match.group(1))
                if amount is not None:
                    return abs(amount)
        return None

    def _classify_amount(self, amount: float, text: str) -> Tuple[Optional[float], Optional[float]]:
        upper = text.upper()
        if re.search(
            r"\b(DBT\s+CRD|POS|C#|CHECK|FEE|PAYMENT|PURCHASE|BILLING|WITHDRAWAL|SUBTRACTION|TRANSFER\s+TO)\b",
            upper,
        ):
            return None, amount
        if re.search(
            r"\b(MERCH\s+DEP|AMEX\s+DEP|ZOHO\s+PAYME|DEPOSIT|CREDIT|ADDITION|TRANSFER\s+FROM)\b",
            upper,
        ):
            return amount, None
        return amount, None

    def _split_date_from_row(self, row: List[str]) -> Tuple[Optional[str], str]:
        if not row:
            return None, ""
        first_cell = str(row[0]).strip()
        match = _DATE_START_RE.match(first_cell)
        if match:
            rest = match.group("rest").strip()
            desc_cells = [rest, *[str(cell).strip() for cell in row[1:]]]
            return match.group("date"), " ".join(cell for cell in desc_cells if cell)
        match = _DATE_START_RE.match(self._row_text(row))
        if not match:
            return None, ""
        return match.group("date"), match.group("rest").strip()

    def _row_has_start_date(self, row: List[str]) -> bool:
        first = str(row[0]).strip() if row else ""
        return bool(_DATE_START_RE.match(first) or _DATE_START_RE.match(self._row_text(row)))

    def _is_header_or_noise(self, row: List[str]) -> bool:
        text = self._row_text(row).lower()
        if not text:
            return True
        return bool(
            re.search(r"\bdate\b.*\bdescription\b.*\b(additions|subtractions)\b", text)
            or "activity in date order" in text
            or ("page " in text and "of " in text)
        )

    def _is_metadata_line(self, line: str) -> bool:
        return bool(
            re.search(
                r"(washington\s+trust|watrust|member\s+fdic|\bfdic\b|statement|account\s+number|activity\s+in\s+date\s+order|daily\s+balance|summary|beginning\s+balance|ending\s+balance|additions|subtractions|total\s+days|^page\s+\d+|^page\s*$|^tube$|^you$)",
                line,
                re.IGNORECASE,
            )
        )

    def _looks_like_address(self, line: str) -> bool:
        return bool(
            re.search(r"\d+\s+\S+", line)
            or re.search(r"\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b", line)
        )

    def _text(self) -> str:
        if self.context.raw_text:
            return self.context.raw_text
        return "\n".join(self._lines())

    def _lines(self) -> List[str]:
        if self.context.raw_text:
            return [
                line.strip()
                for line in self.context.raw_text.splitlines()
                if line.strip()
            ]
        return [
            self._row_text(row)
            for row in self.context.rows
            if row and any(str(cell).strip() for cell in row)
        ]

    def _row_text(self, row: List[str]) -> str:
        return " ".join(str(cell).strip() for cell in row if str(cell).strip()).strip()

    def _remove_amounts(self, text: str) -> str:
        return re.sub(r"\s+", " ", _MONEY_RE.sub("", text)).strip()

    def _parse_statement_date(self, raw: str) -> Optional[str]:
        return parse_date(raw, statement_year=self._statement_year())

    def _parse_output_date(self, raw: Optional[str]) -> Optional[str]:
        if not raw:
            return None
        match = re.match(r"(?P<month>\d{2})/(?P<day>\d{2})/(?P<year>\d{4})", str(raw))
        if match:
            return f"{match.group('year')}-{match.group('month')}-{match.group('day')}"
        return parse_date(str(raw), statement_year=self._statement_year())

    def _sort_transactions(self, transactions: List[Transaction]) -> List[Transaction]:
        return sorted(transactions, key=lambda txn: txn.date or "")

    def _sort_structured_transactions(self, transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sorted_transactions = sorted(
            transactions,
            key=lambda txn: self._parse_output_date(txn.get("date")) or "",
        )
        for idx, transaction in enumerate(sorted_transactions, start=1):
            transaction["seq"] = idx
        return sorted_transactions

    def _statement_year(self) -> Optional[int]:
        if self.context.statement_year:
            return self.context.statement_year
        text = self._text()
        period_match = re.search(r"\b\d{1,2}/\d{1,2}/(?P<year>\d{4})\b", text)
        if period_match:
            return int(period_match.group("year"))
        short_year_match = re.search(r"\b\d{1,2}/\d{1,2}/(?P<year>\d{2})\b", text)
        if short_year_match:
            return 2000 + int(short_year_match.group("year"))
        return None

    def _format_output_date(self, iso_date: Optional[str]) -> Optional[str]:
        if not iso_date:
            return None
        match = re.match(r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})", iso_date)
        if not match:
            return iso_date
        return f"{match.group('month')}/{match.group('day')}/{match.group('year')}"


register_parser(_BANK_ID, WashingtonTrustBankParser)
register_parser("WASHINGTON_TRUST", WashingtonTrustBankParser)
register_parser("WATRUST", WashingtonTrustBankParser)
register_template_parser(_TEMPLATE_ID, WashingtonTrustBankParser)
