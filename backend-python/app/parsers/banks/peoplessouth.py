"""PeopleSouth Bank parser."""

import re
from typing import Any, Dict, List, Optional, Tuple

from app.models.schemas import Transaction
from app.parsers.layouts.signed_amount import SignedAmountParser
from app.parsers.registry import register_parser, register_template_parser
from app.parsers.result import ParseResult, StatementMetadata
from app.services.date_utils import parse_date
from app.services.postprocessor import calculate_confidence


_DATE_START_RE = re.compile(r"^\s*(\d{1,2}/\d{1,2})\b\s*(.*)$")
_MONEY_RE = re.compile(r"\$?\s*\(?\d[\d,]*\.\d{2}\)?(?:-SC|-)?")
_CHECK_ROW_RE = re.compile(
    r"^\s*(?P<date>\d{1,2}/\d{1,2})\s+"
    r"(?P<check>[A-Za-z0-9-]+\*?)\s+"
    r"\$?\s*(?P<amount>\d[\d,]*\.\d{2})\s*$"
)

_SKIP_LINE_PATTERNS = [
    r"member\s+fdic\s+notice",
    r"business\s+checking\s+\d+\s+\(continued\)",
    r"activity\s+in\s+date\s+order",
    r"date\s+description\s+amount",
    r"\*\s+denotes\s+missing\s+check\s+numbers",
    r"^\s*\*+\s*$",
    r"breakdown\s+of\s+total\s+service\s+charge\s+transaction",
    r"overdraft\s+item\s+fees\s+year\s+to\s+date",
    r"substitute\s+image\s*/\s*virtual\s+document",
]


class PeopleSouthParser(SignedAmountParser):
    """Parser trained for PeopleSouth business checking statements."""

    parser_id = "peoplessouth_signed_amount"

    def extract_metadata(self) -> StatementMetadata:
        return self._extract_peoplessouth_metadata()

    def extract_transactions(self) -> List[Transaction]:
        transactions, _ = self._extract_activity_transactions()
        return transactions

    def parse(self) -> ParseResult:
        metadata = self._extract_peoplessouth_metadata()
        transactions, transaction_rows = self._extract_activity_transactions()
        checks_register = self._extract_checks_register()
        validation_errors = self._validate(metadata, transactions)

        structured_transactions = []
        for idx, (transaction, transaction_type) in enumerate(transaction_rows, start=1):
            structured_transactions.append({
                "seq": idx,
                "date": transaction.date,
                "description": transaction.description,
                "debit": transaction.debit,
                "credit": transaction.credit,
                "balance": transaction.balance,
                "transaction_type": transaction_type,
            })

        structured_output = {
            "bank_name": "PeoplesSouth Bank",
            "customer_name": metadata.customer_name,
            "customer_address": metadata.customer_address,
            "account_number": metadata.account_number,
            "account_type": metadata.account_type or "BUSINESS CHECKING",
            "statement_date": metadata.statement_date,
            "period_start": metadata.statement_start_date,
            "period_end": metadata.statement_end_date,
            "opening_balance": metadata.opening_balance,
            "closing_balance": metadata.closing_balance,
            "total_credits": metadata.total_credits,
            "credit_count": metadata.credit_count,
            "total_debits": metadata.total_debits,
            "debit_count": metadata.debit_count,
            "service_charge": metadata.service_charge,
            "overdraft_fees_this_period": metadata.overdraft_fees_this_period,
            "overdraft_fees_ytd": metadata.overdraft_fees_ytd,
            "returned_item_fees_this_period": metadata.returned_item_fees_this_period,
            "returned_item_fees_ytd": metadata.returned_item_fees_ytd,
            "transactions": structured_transactions,
            "checks_register": checks_register,
        }
        if validation_errors:
            structured_output["validation_errors"] = validation_errors

        return ParseResult(
            metadata=metadata,
            transactions=transactions,
            confidence=calculate_confidence([txn.dict() for txn in transactions]),
            parser_id=self.parser_id,
            bank_id=metadata.bank_id,
            template_id=self.context.template_id,
            checks_register=checks_register,
            validation_errors=validation_errors,
            extra={"peoplessouth_output": structured_output},
        )

    def _extract_peoplessouth_metadata(self) -> StatementMetadata:
        text = self._text()
        lines = self._lines()
        period_start, period_end = self._extract_period(text)
        customer_name, customer_address = self._extract_customer_block(lines)
        credit_count, total_credits = self._extract_count_total(text, "Credits")
        debit_count, total_debits = self._extract_count_total(text, "Debits")

        return StatementMetadata(
            bank_id=self.context.bank_id or "PEOPLESOUTH",
            bank_name="PeoplesSouth Bank",
            account_number=self._extract_account_number(text),
            account_holder=customer_name,
            customer_name=customer_name,
            customer_address=customer_address,
            account_type="BUSINESS CHECKING",
            statement_date=self._extract_statement_date(text),
            statement_start_date=period_start,
            statement_end_date=period_end,
            opening_balance=self._extract_labeled_amount(text, "Previous Balance"),
            closing_balance=self._extract_labeled_amount(text, "Current Balance"),
            current_balance=self._extract_labeled_amount(text, "Current Balance"),
            total_credits=total_credits,
            credit_count=credit_count,
            total_debits=total_debits,
            debit_count=debit_count,
            service_charge=self._extract_labeled_amount(text, "Service Charge"),
            overdraft_fees_this_period=self._extract_fee_table_amount(
                text, "Total Overdraft Fees", 0
            ),
            overdraft_fees_ytd=self._extract_fee_table_amount(
                text, "Total Overdraft Fees", 1
            ),
            returned_item_fees_this_period=self._extract_fee_table_amount(
                text, "Total Returned Item Fees", 0
            ),
            returned_item_fees_ytd=self._extract_fee_table_amount(
                text, "Total Returned Item Fees", 1
            ),
        )

    def _extract_activity_transactions(self) -> Tuple[List[Transaction], List[Tuple[Transaction, str]]]:
        lines = self._activity_lines()
        transactions: List[Transaction] = []
        transaction_rows: List[Tuple[Transaction, str]] = []

        for line in lines:
            if self._should_skip_line(line):
                continue

            date_match = _DATE_START_RE.match(line)
            if not date_match:
                if transactions:
                    continuation = self._clean_continuation(line)
                    if continuation:
                        previous = transactions[-1]
                        previous.description = (
                            f"{previous.description} {continuation}".strip()
                        )
                continue

            raw_date, remainder = date_match.groups()
            money_matches = list(_MONEY_RE.finditer(remainder))
            if len(money_matches) < 2:
                continue

            amount_match = money_matches[-2]
            balance_match = money_matches[-1]
            raw_amount = amount_match.group()
            raw_balance = balance_match.group()
            amount = self._parse_money(raw_amount)
            balance = self._parse_money(raw_balance)
            if amount is None or balance is None:
                continue

            description = remainder[:amount_match.start()].strip()
            description = self._normalize_description(description)
            if not description:
                description = remainder.strip()

            is_debit = self._is_debit_amount(raw_amount)
            debit = abs(amount) if is_debit else None
            credit = abs(amount) if not is_debit else None
            date_str = self._parse_statement_date(raw_date)
            transaction_type = self._classify_transaction(description, debit, credit)

            transaction = Transaction(
                date=date_str,
                description=description,
                debit=debit,
                credit=credit,
                balance=abs(balance),
            )
            transactions.append(transaction)
            transaction_rows.append((transaction, transaction_type))

        return transactions, transaction_rows

    def _extract_checks_register(self) -> List[Dict[str, Any]]:
        lines = self._checks_lines()
        checks: List[Dict[str, Any]] = []

        for line in lines:
            if self._should_skip_line(line):
                continue
            match = _CHECK_ROW_RE.match(line)
            if not match:
                continue

            check_number = match.group("check")
            checks.append({
                "date": self._parse_statement_date(match.group("date")),
                "check_number": check_number.rstrip("*"),
                "amount": self._parse_money(match.group("amount")),
                "missing_sequence_flag": check_number.endswith("*"),
            })

        return checks

    def _validate(
        self,
        metadata: StatementMetadata,
        transactions: List[Transaction],
    ) -> List[str]:
        errors: List[str] = []
        credit_sum = round(sum(float(txn.credit or 0) for txn in transactions), 2)
        debit_sum = round(sum(float(txn.debit or 0) for txn in transactions), 2)
        credit_count = sum(1 for txn in transactions if txn.credit)
        debit_count = sum(1 for txn in transactions if txn.debit)

        if (
            metadata.opening_balance is not None
            and metadata.closing_balance is not None
        ):
            expected = round(metadata.opening_balance + credit_sum - debit_sum, 2)
            if abs(expected - metadata.closing_balance) > 0.05:
                errors.append(
                    "Balance chain failed: "
                    f"{metadata.opening_balance} + {credit_sum} - {debit_sum} "
                    f"= {expected}, expected {metadata.closing_balance}."
                )

        if metadata.total_credits is not None and abs(credit_sum - metadata.total_credits) > 0.05:
            errors.append(
                f"Credit total mismatch: transactions={credit_sum}, header={metadata.total_credits}."
            )
        if metadata.total_debits is not None and abs(debit_sum - metadata.total_debits) > 0.05:
            errors.append(
                f"Debit total mismatch: transactions={debit_sum}, header={metadata.total_debits}."
            )
        if metadata.credit_count is not None and credit_count != metadata.credit_count:
            errors.append(
                f"Credit count mismatch: transactions={credit_count}, header={metadata.credit_count}."
            )
        if metadata.debit_count is not None and debit_count != metadata.debit_count:
            errors.append(
                f"Debit count mismatch: transactions={debit_count}, header={metadata.debit_count}."
            )

        service_charge_debits = [
            float(txn.debit)
            for txn in transactions
            if txn.debit is not None and "service charge" in txn.description.lower()
        ]
        if metadata.service_charge is not None:
            if not service_charge_debits:
                errors.append("Service charge transaction not found.")
            elif all(abs(debit - metadata.service_charge) > 0.05 for debit in service_charge_debits):
                errors.append(
                    "Service charge mismatch: "
                    f"transactions={service_charge_debits}, header={metadata.service_charge}."
                )

        return errors

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
            " ".join(str(cell) for cell in row if str(cell).strip()).strip()
            for row in self.context.rows
            if row and any(str(cell).strip() for cell in row)
        ]

    def _activity_lines(self) -> List[str]:
        lines = self._lines()
        start = 0
        end = len(lines)
        for idx, line in enumerate(lines):
            if re.search(r"activity\s+in\s+date\s+order", line, re.IGNORECASE):
                start = idx + 1
                break
        for idx in range(start, len(lines)):
            if re.search(r"checks\s+in\s+number\s+order", lines[idx], re.IGNORECASE):
                end = idx
                break
            if re.search(r"substitute\s+image\s*/\s*virtual\s+document", lines[idx], re.IGNORECASE):
                end = idx
                break
        return lines[start:end]

    def _checks_lines(self) -> List[str]:
        lines = self._lines()
        start = None
        for idx, line in enumerate(lines):
            if re.search(r"checks\s+in\s+number\s+order", line, re.IGNORECASE):
                start = idx + 1
                break
        if start is None:
            return []
        checks = []
        for line in lines[start:]:
            if re.search(r"substitute\s+image\s*/\s*virtual\s+document", line, re.IGNORECASE):
                break
            checks.append(line)
        return checks

    def _extract_customer_block(self, lines: List[str]) -> Tuple[Optional[str], Optional[str]]:
        for idx, line in enumerate(lines[:80]):
            if re.fullmatch(r"\d{7}", line.strip()):
                name = lines[idx + 1].strip() if idx + 1 < len(lines) else None
                street = lines[idx + 2].strip() if idx + 2 < len(lines) else ""
                city = lines[idx + 3].strip() if idx + 3 < len(lines) else ""
                address = " ".join(part for part in [street, city] if part)
                return name, address or None
        return None, None

    def _extract_account_number(self, text: str) -> Optional[str]:
        match = re.search(r"Account\s+Number\s*[:\s]*([0-9]{6,})", text, re.IGNORECASE)
        return match.group(1) if match else None

    def _extract_statement_date(self, text: str) -> Optional[str]:
        match = re.search(r"\bDate\s+(\d{1,2}/\d{1,2}/\d{2,4})\b", text, re.IGNORECASE)
        if match:
            return self._parse_statement_date(match.group(1))
        return None

    def _extract_period(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        match = re.search(
            r"Statement\s+Dates?\s+(\d{1,2}/\d{1,2}/\d{2,4})\s+thru\s+(\d{1,2}/\d{1,2}/\d{2,4})",
            text,
            re.IGNORECASE,
        )
        if not match:
            return None, None
        return (
            self._parse_statement_date(match.group(1)),
            self._parse_statement_date(match.group(2)),
        )

    def _extract_labeled_amount(self, text: str, label: str) -> Optional[float]:
        match = re.search(
            rf"{re.escape(label)}\s*[:\s]*\$?\s*([0-9,]+\.\d{{2}})",
            text,
            re.IGNORECASE,
        )
        if match:
            return self._parse_money(match.group(1))
        return None

    def _extract_count_total(self, text: str, label: str) -> Tuple[Optional[int], Optional[float]]:
        match = re.search(
            rf"\b(\d+)\s+{re.escape(label)}\s+\$?\s*([0-9,]+\.\d{{2}})",
            text,
            re.IGNORECASE,
        )
        if not match:
            return None, None
        return int(match.group(1)), self._parse_money(match.group(2))

    def _extract_fee_table_amount(self, text: str, label: str, amount_index: int) -> Optional[float]:
        match = re.search(
            rf"{re.escape(label)}[^\n\r]*?((?:\$?\s*[0-9,]+\.\d{{2}}\s*){{1,2}})",
            text,
            re.IGNORECASE,
        )
        if not match:
            return None
        amounts = _MONEY_RE.findall(match.group(0))
        if amount_index >= len(amounts):
            return None
        return self._parse_money(amounts[amount_index])

    def _parse_statement_date(self, raw: str) -> Optional[str]:
        return parse_date(raw, statement_year=self.context.statement_year)

    def _parse_money(self, raw: str) -> Optional[float]:
        if not raw:
            return None
        cleaned = raw.strip()
        negative = cleaned.endswith("-") or cleaned.upper().endswith("-SC")
        cleaned = re.sub(r"(?i)-SC$", "", cleaned)
        cleaned = cleaned.rstrip("-")
        cleaned = cleaned.replace("$", "").replace(",", "").replace("(", "-").replace(")", "")
        cleaned = cleaned.strip()
        try:
            value = abs(float(cleaned))
        except ValueError:
            return None
        return -value if negative else value

    def _is_debit_amount(self, raw_amount: str) -> bool:
        raw = raw_amount.strip().upper()
        return raw.endswith("-") or raw.endswith("-SC")

    def _normalize_description(self, description: str) -> str:
        return re.sub(r"\s+", " ", description).strip()

    def _clean_continuation(self, line: str) -> str:
        if self._should_skip_line(line):
            return ""
        return self._normalize_description(line)

    def _should_skip_line(self, line: str) -> bool:
        return any(re.search(pattern, line, re.IGNORECASE) for pattern in _SKIP_LINE_PATTERNS)

    def _classify_transaction(
        self,
        description: str,
        debit: Optional[float],
        credit: Optional[float],
    ) -> str:
        upper = description.upper()
        if "SERVICE CHARGE" in upper:
            return "service_charge"
        if "OVERDRAFT" in upper:
            return "overdraft_fee"
        if upper.startswith("CHECK") or "CHECK NO" in upper:
            return "check"
        if "TRANSFER" in upper:
            return "transfer"
        if "POS CRE" in upper:
            return "pos_credit"
        if "LOAN PAY" in upper:
            return "loan_payment"
        if "DBT CRD" in upper or "DEBIT" in upper:
            return "card_debit"
        if credit is not None:
            return "credit"
        if debit is not None:
            return "debit"
        return "unknown"


register_parser("PEOPLESOUTH", PeopleSouthParser)
register_parser("PEOPLESOUTH_BANK", PeopleSouthParser)
register_template_parser("peoplessouth_signed_amount_v1", PeopleSouthParser)
