"""Timberland Bank parser."""

import re
from typing import Any, Dict, List, Optional, Tuple

from app.models.schemas import Transaction
from app.parsers.base import BaseParser
from app.parsers.registry import register_parser, register_template_parser
from app.parsers.result import ParseResult, StatementMetadata
from app.services.amount_utils import clean_amount
from app.services.date_utils import parse_date
from app.services.postprocessor import calculate_confidence


_BANK_ID = "TIMBERLAND_BANK"
_BANK_NAME = "Timberland Bank"
_TEMPLATE_ID = "timberland_bank_v1"

_DATE_START_RE = re.compile(
    r"^\s*(?:[^A-Za-z\n]{0,16})?"
    r"(?P<date>\d{1,2}/\d{1,3})(?!/)\b"
    r"\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_MONEY_RE = re.compile(r"\$?\s*\d[\d,]*\.\d{2}-?")
_ACH_CODE_RE = re.compile(r"^(?:CCD|PPD|WEB|CTX)\b", re.IGNORECASE)
_CITY_STATE_ZIP_RE = re.compile(r"\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b")


class TimberlandBankParser(BaseParser):
    """Parser for Timberland Bank scanned checking statements."""

    parser_id = _TEMPLATE_ID

    def extract_metadata(self) -> StatementMetadata:
        return self._extract_metadata()

    def extract_transactions(self) -> List[Transaction]:
        transactions, _ = self._extract_section_transactions()
        return transactions

    def parse(self) -> ParseResult:
        metadata = self._extract_metadata()
        transactions, structured_transactions = self._extract_section_transactions()
        checks_register = self._extract_checks_register()
        daily_balances = self._extract_daily_balances()
        validation_errors = self._validate(metadata, transactions)

        return ParseResult(
            metadata=metadata,
            transactions=transactions,
            confidence=calculate_confidence([txn.dict() for txn in transactions]),
            parser_id=self.parser_id,
            bank_id=_BANK_ID,
            template_id=self.context.template_id or _TEMPLATE_ID,
            checks_register=checks_register,
            validation_errors=validation_errors,
            extra={
                "timberland_bank_output": {
                    "bank_name": metadata.bank_name,
                    "account_holder": {
                        "name": metadata.customer_name,
                        "address": metadata.customer_address,
                    },
                    "account_type": metadata.account_type,
                    "account_number": metadata.account_number,
                    "statement_period": {
                        "start_date": metadata.statement_start_date,
                        "end_date": metadata.statement_end_date,
                    },
                    "summary_financials": {
                        "previous_balance": metadata.opening_balance,
                        "current_balance": metadata.current_balance,
                        "total_credits": metadata.total_credits,
                        "credit_count": metadata.credit_count,
                        "total_debits": metadata.total_debits,
                        "debit_count": metadata.debit_count,
                    },
                    "transactions": structured_transactions,
                    "checks_cleared": checks_register,
                    "daily_balances": daily_balances,
                    "fee_summary": {
                        "overdraft_fees_this_period": metadata.overdraft_fees_this_period,
                        "overdraft_fees_ytd": metadata.overdraft_fees_ytd,
                        "returned_item_fees_this_period": metadata.returned_item_fees_this_period,
                        "returned_item_fees_ytd": metadata.returned_item_fees_ytd,
                    },
                }
            },
        )

    def _extract_metadata(self) -> StatementMetadata:
        text = self._text()
        lines = self._lines()
        customer_name, customer_address = self._extract_customer_block(lines)
        statement_start, statement_end = self._extract_period(text)
        account_type, account_number = self._extract_account_details(text, lines)
        credit_count, total_credits = self._extract_counted_total(text, "Deposits/Credits")
        debit_count, total_debits = self._extract_counted_total(text, "Checks/Debits")
        overdraft_period, overdraft_ytd = self._extract_fee_pair(text, "overdraft item fees")
        returned_period, returned_ytd = self._extract_fee_pair(text, "return item fees")

        current_balance = self._extract_labeled_amount(text, ["Current Balance"])
        return StatementMetadata(
            bank_id=_BANK_ID,
            bank_name=_BANK_NAME,
            account_number=account_number,
            account_holder=customer_name,
            customer_name=customer_name,
            customer_address=customer_address,
            account_type=account_type,
            statement_start_date=statement_start,
            statement_end_date=statement_end,
            opening_balance=self._extract_labeled_amount(text, ["Previous Balance"]),
            closing_balance=current_balance,
            current_balance=current_balance,
            total_credits=total_credits,
            credit_count=credit_count,
            total_debits=total_debits,
            debit_count=debit_count,
            service_charge=self._extract_labeled_amount(text, ["Service Charge"]),
            overdraft_fees_this_period=overdraft_period,
            overdraft_fees_ytd=overdraft_ytd,
            returned_item_fees_this_period=returned_period,
            returned_item_fees_ytd=returned_ytd,
        )

    def _extract_section_transactions(self) -> Tuple[List[Transaction], List[Dict[str, Any]]]:
        transactions: List[Transaction] = []
        structured: List[Dict[str, Any]] = []
        section: Optional[str] = None
        current: Optional[Dict[str, Any]] = None

        def flush() -> None:
            nonlocal current
            if not current or not current.get("section"):
                current = None
                return
            parsed = self._parse_transaction_group(current)
            current = None
            if parsed is None:
                return
            transaction, output = parsed
            transactions.append(transaction)
            output["seq"] = len(structured) + 1
            structured.append(output)

        for line in self._lines():
            lowered = line.lower()
            if self._is_statement_code_summary(line):
                flush()
                break
            if self._is_section_header(line, "credits"):
                flush()
                section = "credit"
                continue
            if self._is_section_header(line, "debits"):
                flush()
                section = "debit"
                continue
            if section is None:
                continue

            date_match = self._date_start_match(line)
            if date_match and self._parse_statement_date(date_match.group("date")):
                flush()
                current = {
                    "date": date_match.group("date"),
                    "section": section,
                    "lines": [line],
                }
                continue
            if (
                current
                and re.fullmatch(r"\d{2,8}", self._clean_text(line))
                and re.search(r"conf\s*#", " ".join(current.get("lines", [])), re.IGNORECASE)
            ):
                current["lines"].append(line)
                continue
            if self._is_transaction_noise(line):
                continue
            if current and line.strip():
                current["lines"].append(line)

        flush()
        return transactions, structured

    def _parse_transaction_group(
        self,
        group: Dict[str, Any],
    ) -> Optional[Tuple[Transaction, Dict[str, Any]]]:
        lines = [str(line).strip() for line in group.get("lines", []) if str(line).strip()]
        if not lines:
            return None

        source_text = " ".join(lines)
        amount = self._extract_last_amount(source_text)
        if amount is None:
            return None

        section = group.get("section")
        debit = abs(amount) if section == "debit" else None
        credit = abs(amount) if section == "credit" else None
        date_iso = self._parse_statement_date(str(group.get("date") or ""))
        if not date_iso:
            return None

        description = self._description_from_group(lines)
        if not description:
            description = "Credit transaction" if section == "credit" else "Debit transaction"

        transaction = Transaction(
            date=date_iso,
            description=description,
            debit=debit,
            credit=credit,
            balance=None,
        )
        output = {
            "date": date_iso,
            "description": description,
            "credit": credit,
            "debit": debit,
            "running_balance": None,
            "source_text": source_text,
        }
        if section == "debit" and "overdraft fee" in description.lower():
            output["fee_type"] = "OVERDRAFT"
        return transaction, output

    def _description_from_group(self, lines: List[str]) -> str:
        parts: List[str] = []
        for idx, raw_line in enumerate(lines):
            line = raw_line.strip()
            if idx == 0:
                date_match = self._date_start_match(line)
                if date_match:
                    line = date_match.group("rest").strip()
            line = self._remove_amounts(line)
            line = re.sub(r"\b(?:Date|Description|Amount)\b", " ", line, flags=re.IGNORECASE)
            line = self._clean_text(line)
            if not line:
                continue
            if _ACH_CODE_RE.match(line):
                parts.append(line.split()[0].upper())
                continue
            parts.append(line)
        return re.sub(r"\s+", " ", " ".join(parts)).strip(" |")

    def _extract_checks_register(self) -> List[Dict[str, Any]]:
        checks: List[Dict[str, Any]] = []
        seen = set()
        in_checks = False

        for line in self._lines():
            if re.search(r"checks\s+cleared", line, re.IGNORECASE):
                in_checks = True
                continue
            if not in_checks:
                continue
            if re.search(r"daily\s+balance|denotes\s+missing|privacy|member\s+fdic", line, re.IGNORECASE):
                break
            if re.search(r"\bdate\b.*check\s+no.*amount", line, re.IGNORECASE):
                continue

            normalized = self._clean_check_line(line)
            date_matches = list(re.finditer(r"\d{1,2}/\d{1,3}", normalized))
            for idx, date_match in enumerate(date_matches):
                chunk_end = date_matches[idx + 1].start() if idx + 1 < len(date_matches) else len(normalized)
                chunk = normalized[date_match.end():chunk_end].strip()
                detail_match = re.match(
                    r"(?P<check>\d(?:\s?\d){2,5}\*{0,2})\s+"
                    r"(?P<amount>\d[\d,\s]*\.\d{2})",
                    chunk,
                )
                if not detail_match:
                    continue
                date_iso = self._parse_statement_date(date_match.group())
                amount = self._parse_money(detail_match.group("amount"))
                if not date_iso or amount is None:
                    continue
                raw_check = detail_match.group("check").strip()
                check_number = re.sub(r"\D", "", raw_check)
                if not check_number:
                    continue
                key = (date_iso, check_number, round(abs(amount), 2))
                if key in seen:
                    continue
                seen.add(key)
                checks.append({
                    "date": date_iso,
                    "check_number": check_number,
                    "amount": abs(amount),
                    "has_gap_flag": "*" in raw_check,
                })
        return checks

    def _extract_daily_balances(self) -> List[Dict[str, Any]]:
        balances: List[Dict[str, Any]] = []
        seen = set()
        in_daily_balance = False

        for line in self._lines():
            if re.search(r"daily\s+balance\s+information", line, re.IGNORECASE):
                in_daily_balance = True
                continue
            if not in_daily_balance:
                continue
            if re.search(r"\bdate\b.*\bbalance\b", line, re.IGNORECASE):
                continue
            for match in re.finditer(
                r"(?P<date>\d{1,2}/\d{1,3})\s+(?P<balance>\d[\d,\s]*\.\d{2}-?)",
                self._clean_check_line(line),
            ):
                date_iso = self._parse_statement_date(match.group("date"))
                balance = self._parse_money(match.group("balance"))
                if not date_iso or balance is None:
                    continue
                key = (date_iso, round(balance, 2))
                if key in seen:
                    continue
                seen.add(key)
                balances.append({"date": date_iso, "closing_balance": balance})
        return balances

    def _extract_period(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        match = re.search(
            r"Statement\s+Dates?\D{0,20}"
            r"(?P<start>\d{1,2}/\d{1,2}/\d{2,4})\s*(?:thru|through|to|-)?\D{0,20}"
            r"(?P<end>\d{1,2}/\d{1,2}/\d{2,4})",
            text,
            re.IGNORECASE,
        )
        if not match:
            return None, None
        return (
            self._parse_statement_date(match.group("start")),
            self._parse_statement_date(match.group("end")),
        )

    def _extract_customer_block(self, lines: List[str]) -> Tuple[Optional[str], Optional[str]]:
        for idx, line in enumerate(lines[:80]):
            if not re.fullmatch(r"\d{7}", re.sub(r"\D", "", line)):
                continue
            block: List[str] = []
            for candidate in lines[idx + 1: idx + 6]:
                cleaned = self._clean_text(candidate)
                if not cleaned:
                    continue
                block.append(cleaned)
                if _CITY_STATE_ZIP_RE.search(cleaned):
                    break
            if block:
                return block[0], " ".join(block[1:]) or None
        return None, None

    def _extract_account_details(
        self,
        text: str,
        lines: List[str],
    ) -> Tuple[Optional[str], Optional[str]]:
        account_type = None
        for line in lines[:100]:
            match = re.search(r"\b((?:BUSINESS|PERSONAL)\s+CHECKING)\b", line, re.IGNORECASE)
            if match:
                account_type = match.group(1).upper()
                break

        account_number = None
        match = re.search(
            r"Account\s+Number[^Xx*\d]{0,30}([Xx*\d]{4,20})",
            text,
            re.IGNORECASE,
        )
        if match:
            account_number = match.group(1).upper()
        return account_type, account_number

    def _extract_counted_total(self, text: str, label: str) -> Tuple[Optional[int], Optional[float]]:
        match = re.search(
            rf"(?P<count>\d{{1,4}})[^\w\n]{{0,10}}{re.escape(label)}"
            rf"[^\d\n]{{0,40}}(?P<amount>\d[\d,]*\.\d{{2}}-?)",
            text,
            re.IGNORECASE,
        )
        if not match:
            return None, None
        return int(match.group("count")), self._parse_money(match.group("amount"))

    def _extract_fee_pair(self, text: str, label: str) -> Tuple[Optional[float], Optional[float]]:
        match = re.search(
            rf"{re.escape(label)}.*?\$?\s*(?P<period>\d[\d,]*\.\d{{2}}).*?"
            rf"\$?\s*(?P<ytd>\d[\d,]*\.\d{{2}})",
            text,
            re.IGNORECASE,
        )
        if not match:
            return None, None
        return self._parse_money(match.group("period")), self._parse_money(match.group("ytd"))

    def _extract_labeled_amount(self, text: str, labels: List[str]) -> Optional[float]:
        for label in labels:
            match = re.search(
                rf"{re.escape(label)}\D{{0,35}}(?P<amount>\d[\d,]*\.\d{{2}}-?|\.\d{{2}}-?)",
                text,
                re.IGNORECASE,
            )
            if match:
                return self._parse_money(match.group("amount"))
        return None

    def _validate(
        self,
        metadata: StatementMetadata,
        transactions: List[Transaction],
    ) -> List[str]:
        warnings: List[str] = []
        credit_sum = round(sum(float(txn.credit or 0) for txn in transactions), 2)
        debit_sum = round(sum(float(txn.debit or 0) for txn in transactions), 2)

        if metadata.total_credits is not None and abs(credit_sum - metadata.total_credits) > 1.00:
            warnings.append(
                f"Credit total mismatch: transactions={credit_sum}, statement={metadata.total_credits}."
            )
        if metadata.total_debits is not None and debit_sum > metadata.total_debits + 1.00:
            warnings.append(
                f"Debit total exceeds statement total: transactions={debit_sum}, statement={metadata.total_debits}."
            )
        return warnings

    def _is_section_header(self, line: str, section: str) -> bool:
        cleaned = re.sub(r"[^a-z]", "", line.lower())
        return cleaned == section or (
            cleaned.endswith(section)
            and len(cleaned) <= len(section) + 2
        )

    def _is_statement_code_summary(self, line: str) -> bool:
        return bool(re.search(r"statement\s+code\s+summary", line, re.IGNORECASE))

    def _is_transaction_noise(self, line: str) -> bool:
        lowered = line.lower()
        return bool(
            re.search(r"\bdate\b.*\bdescription\b.*\bamount\b", lowered)
            or "business checking" in lowered
            or "businesschecking" in lowered
            or "continued" in lowered
            or "timberland" in lowered
            or re.search(r"\bdate\b.*\bpage\b", lowered)
            or re.fullmatch(r"a?bank", lowered.strip())
            or "federal law requires" in lowered
            or "privacy policy" in lowered
            or "upon request" in lowered
            or re.fullmatch(r"[\W_0-9| ]{1,20}", line.strip())
        )

    def _lines(self) -> List[str]:
        if self.context.raw_text:
            return [line.strip() for line in self.context.raw_text.splitlines() if line.strip()]
        return [
            self._row_text(row)
            for row in self.context.rows
            if row and any(str(cell).strip() for cell in row)
        ]

    def _text(self) -> str:
        return "\n".join(self._lines())

    def _row_text(self, row: List[str]) -> str:
        return " | ".join(str(cell).strip() for cell in row if str(cell).strip()).strip()

    def _clean_text(self, text: str) -> str:
        text = text.replace("|", " ")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _remove_amounts(self, text: str) -> str:
        return re.sub(r"\s+", " ", _MONEY_RE.sub(" ", text)).strip()

    def _extract_last_amount(self, text: str) -> Optional[float]:
        matches = list(_MONEY_RE.finditer(text))
        for match in reversed(matches):
            amount = self._parse_money(match.group())
            if amount is not None:
                return amount
        return None

    def _parse_money(self, raw: str) -> Optional[float]:
        if not raw:
            return None
        cleaned = re.sub(r"(?<=\d)\s+(?=\d)", "", raw.strip())
        if cleaned.startswith("."):
            cleaned = "0" + cleaned
        return clean_amount(cleaned)

    def _parse_statement_date(self, raw: str) -> Optional[str]:
        date = self._normalize_short_date(raw)
        return parse_date(date, statement_year=self._statement_year())

    def _date_start_match(self, line: str) -> Optional[re.Match]:
        match = _DATE_START_RE.match(line)
        if match:
            return match
        fallback = re.search(r"(?P<date>\d{1,2}/\d{1,3})(?!/)\b(?P<rest>.*)$", line)
        if not fallback:
            return None
        prefix = line[:fallback.start()]
        if len(prefix) <= 4 and not re.search(r"[A-Za-z]{2,}", prefix):
            return fallback
        return None

    def _normalize_short_date(self, raw: str) -> str:
        match = re.match(r"\s*(?P<month>\d{1,2})/(?P<day>\d{1,3})", str(raw))
        if not match:
            return str(raw)
        month = match.group("month")
        day = match.group("day")
        if len(month) == 2 and month[0] == month[1] and int(month) > 12:
            month = month[0]
        if len(day) == 3 and day.endswith("0"):
            day = day[:2]
        return f"{month}/{day}"

    def _statement_year(self) -> Optional[int]:
        if self.context.statement_year:
            return self.context.statement_year
        match = re.search(r"\b\d{1,2}/\d{1,2}/(?P<year>\d{2,4})\b", self._text())
        if not match:
            return None
        year = int(match.group("year"))
        return year if year > 99 else 2000 + year

    def _clean_check_line(self, line: str) -> str:
        line = self._clean_text(line)
        line = re.sub(r"(\d)\.\d\s+(\d{3}\.\d{2})", r"\1,\2", line)
        line = re.sub(r"(?<=\d)\s*\|\s*(?=\d)", " ", line)
        line = re.sub(r"\b2\s+312\b", "2312", line)
        return line


register_parser(_BANK_ID, TimberlandBankParser)
register_parser("TIMBERLAND", TimberlandBankParser)
register_parser("TIMBERLAND_BANK", TimberlandBankParser)
register_template_parser(_TEMPLATE_ID, TimberlandBankParser)
