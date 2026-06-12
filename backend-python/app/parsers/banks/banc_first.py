"""BancFirst Bank statement parser."""

import re
from typing import Any, Dict, List, Optional, Tuple

from app.models.schemas import Transaction
from app.parsers.base import BaseParser
from app.parsers.registry import register_parser, register_template_parser
from app.parsers.result import ParseResult, StatementMetadata
from app.services.date_utils import parse_date
from app.services.postprocessor import calculate_confidence


_DATE_START_RE = re.compile(r"^\s*(\d{1,2}/\d{1,2})\s+")
_MONEY_RE = re.compile(r"([\d,]+\.\d{2}-?)")
_TRAILING_MINUS_RE = re.compile(r"([\d,]+\.\d{2})-")

# Anchors the start of the Activity Description column.
# BancFirst descriptions always begin with one of these known prefixes.
# Everything to the LEFT of this anchor in the remainder is amount columns;
# everything from this anchor rightward is the clean description.
_DESC_ANCHOR_RE = re.compile(
    r"(BANKCARD|INTERNET TRANSFER|POS PURCHASE|OVERDRAFT CHARGE|INSUFFICIENT CHARGE|"
    r"ACCOUNT ANALYSIS|CASH-ARC|LSPD CAPITAL|Byzfunder|Fundomate|EBF HOLDINGS|"
    r"Capital Beer|OKLAHOMATAXPMTS|OG&E|ATT/PAYMENT|OK NATURAL GAS|TRAVELERS|"
    r"PAYPAL|DEPOSIT|REFUND INSUFFICIENT)",
    re.IGNORECASE
)

_SECTION_HEADER_RE = re.compile(r"^\s*(?:-\s*){5,25}(DEPOSITS|CARD ACTIVITY|OTHER DEBITS|CHECKS|DAILY BALANCE SUMMARY)(?:\s*-){5,25}\s*$", re.IGNORECASE)

_SKIP_PATTERNS = [
    r"page\s+\d+",
    r"continued\s+on",
    r"bancfirst\.bank",
    r"bancfirst",
    r"to\s+oklahoma\s+&\s+you",
    r"business\s+essentials",
    r"^\s*date\s*\|\s*(?:deposits|withdrawals|activity|check|balance)",
    r"^\s*-\s*-\s*-", # default dashed lines
]

# Add these at the top of your file with the other compiled regexes
_SEQUENCE_CODE_RE = re.compile(r"^\d \*\d{7}$")
_ADDRESS_SKIP_RE = re.compile(
    r"^(PO BOX|P\.O\. BOX|\d{3,5}\s+\w|\(\d{3}\)|\d{5}(-\d{4})?$)",
    re.IGNORECASE
)
_DBA_RE = re.compile(r"^DBA\s+(.+)$", re.IGNORECASE)

_HEADER_BOILERPLATE_RE = re.compile(
    r"^(Dir\s+\d|"                     # Dir 1 251 13, Dir 1 251 25
    r"BNCF:|"                          # BNCF:0009741
    r"[0-9A-Z]{4,}X[0-9A-Z]+\.005|"  # 10037X0C.005, 11167X0C.005
    r"\d{4}-\d{5}|"                   # 8001-00000, 8002-00000
    r"[A-Z]\d{3}-\d{5}|"             # C001-00000, A021-00000
    r".*\*[A-Z0-9]{4}\*)",            # *8001*, *4001*, *C001*
    re.IGNORECASE
)

_CUSTOMER_BLOCKLIST = [
    "bancfirst", "bncf", "loyal", "oklahoma", "fdic", "member", "msi",
    "24-hour", "automated", "account information", "www.bancfirst",
    "continued", "page", "dir ", "statement", "deposits", "withdrawals",
    "business essentials", "service charge", "enclosures",
]

class BancFirstParser(BaseParser):
    """Parser trained for BancFirst business checking statements."""

    parser_id = "bancfirst_business"

    def extract_metadata(self) -> StatementMetadata:
        return self._extract_bancfirst_metadata()

    def extract_transactions(self) -> List[Transaction]:
        transactions, _, _ = self._extract_all_transactions()
        return transactions

    def parse(self) -> ParseResult:
        metadata = self._extract_bancfirst_metadata()
        transactions, checks, raw_txns = self._extract_all_transactions()
        validation_errors = self._validate(metadata, transactions)

        # Build output structure matching prompt output schema
        structured_output = {
            "bank_name": "BancFirst",
            "account_number": metadata.account_number,
            "customer_name": metadata.customer_name,
            "co_customer_name": metadata.extra.get("co_customer_name") if metadata.extra else None,
            "business_dba": metadata.extra.get("business_dba") if metadata.extra else None,
            "statement_period_start": metadata.statement_start_date,
            "statement_period_end": metadata.statement_end_date,
            "beginning_balance": metadata.opening_balance,
            "ending_balance": metadata.closing_balance,
            "total_credits": metadata.total_credits,
            "total_debits": metadata.total_debits,
            "deposit_count": metadata.credit_count,
            "debit_count": metadata.debit_count,
            "service_charge": metadata.service_charge,
            "transactions": raw_txns,
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
            checks_register=checks,
            validation_errors=validation_errors,
            extra={"bancfirst_output": structured_output},
        )

    def _extract_bancfirst_metadata(self) -> StatementMetadata:
        text = self._text()
        lines = self._lines()
        
        customer_name, co_customer, business_dba = self._extract_customer_block(lines)

        start_date, end_date = self._extract_period(text)
        
        credit_count, total_credits = self._extract_count_total(text, r"Deposits\s*/\s*Misc\s*Credits")
        debit_count, total_debits = self._extract_count_total(text, r"Withdrawals\s*/\s*Misc\s*Debits")

        return StatementMetadata(
            bank_id=self.context.bank_id or "BANCFIRST",
            bank_name="BancFirst",
            account_number=self._extract_account_number(text),
            account_holder=customer_name,
            customer_name=customer_name,
            statement_date=self._extract_statement_date(text),
            statement_start_date=start_date,
            statement_end_date=end_date,
            opening_balance=self._extract_beginning_balance(text),
            closing_balance=self._extract_ending_balance(text),
            current_balance=self._extract_ending_balance(text),
            total_credits=total_credits,
            credit_count=credit_count,
            total_debits=total_debits,
            debit_count=debit_count,
            service_charge=self._extract_labeled_amount(text, "Service Charge"),
            extra={
                "co_customer_name": co_customer,
                "business_dba": business_dba,
            }
        )

    def _extract_all_transactions(self) -> Tuple[List[Transaction], List[Dict[str, Any]], List[Dict[str, Any]]]:
        lines = self._lines()
        transactions: List[Transaction] = []
        checks: List[Dict[str, Any]] = []
        raw_txns: List[Dict[str, Any]] = []

        current_section = None
        statement_month = None
        statement_year = self.context.statement_year
        if self.context.metadata and self.context.metadata.statement_date:
            try:
                date_parts = self.context.metadata.statement_date.split("-")
                statement_year = int(date_parts[0])
                statement_month = int(date_parts[1])
            except:
                pass

        for i, line in enumerate(lines):
            section_match = _SECTION_HEADER_RE.match(line)
            if section_match:
                current_section = section_match.group(1).upper()
                continue

            if not current_section:
                continue

            if self._is_image_caption(line):
                continue

            if current_section in ["DEPOSITS", "OTHER DEBITS", "CARD ACTIVITY"]:
                self._parse_transaction_row(line, current_section, statement_month, statement_year, transactions, raw_txns)
            elif current_section == "CHECKS":
                self._parse_checks_row(line, statement_month, statement_year, transactions, checks, raw_txns)
            elif current_section == "DAILY BALANCE SUMMARY":
                pass # parsing this is optional for transaction output, just balances

        return transactions, checks, raw_txns

    def _parse_transaction_row(
        self,
        line: str,
        section: str,
        statement_month: Optional[int],
        statement_year: Optional[int],
        transactions: List[Transaction],
        raw_txns: List[Dict[str, Any]],
    ):
        if not line.strip() or self._should_skip_line(line):
            return

        date_match = _DATE_START_RE.match(line)
        if not date_match:
            # ── Continuation line (no date at start) ──────────────────────────
            # Examples:
            #   " 513331049020605 CHURCH AVENUE SPIRITS"
            #   " 44-1706376 Church Ave Spirits (DE"
            #   " *****2738 02/04 02:59"
            if raw_txns:
                continuation = line.strip()
                if continuation and not self._should_skip_line(continuation):
                    raw_txns[-1]["description"] += f" {continuation}"
                    if transactions:
                        transactions[-1].description += f" {continuation}"
            return

        raw_date = date_match.group(1)
        # remainder = everything after "MM/DD " e.g. "675.89 BANKCARD 1237/MTOT DEP"
        remainder = line[date_match.end():]

        # ── Step 1: find where the Activity Description column starts ──────────
        # Strategy: search for a known description keyword anchor.
        # Everything to its LEFT is the amount column(s); everything from it
        # rightward is the clean description — no date, no dollar values.
        desc_anchor = _DESC_ANCHOR_RE.search(remainder)

        if desc_anchor:
            amount_part = remainder[: desc_anchor.start()]
            desc = remainder[desc_anchor.start() :].strip()
        else:
            # Fallback for lines whose description doesn't start with a known
            # keyword (e.g. plain "DEPOSIT"). Strip leading amount tokens.
            amount_part = remainder
            desc = ""
            # Remove every money token from left; what's left is the description
            temp = remainder.strip()
            money_tokens = _MONEY_RE.findall(temp)
            for token in money_tokens:
                temp = temp.replace(token, "", 1).strip()
            desc = temp

        # ── Step 2: parse amounts from the amount column portion ───────────────
        amount_values = [self._parse_money(m) for m in _MONEY_RE.findall(amount_part)]
        amount_values = [v for v in amount_values if v is not None]

        deposits = None
        withdrawals = None

        if section == "DEPOSITS":
            # First (and usually only) amount is a credit.
            # Exception: BANKCARD DISC rows in DEPOSITS section have a debit.
            if amount_values:
                if "DISC" in desc.upper():
                    withdrawals = amount_values[0]
                else:
                    deposits = amount_values[0]
            # A second amount (rare) would be a withdrawal
            if len(amount_values) >= 2:
                withdrawals = amount_values[1]
        else:
            # CARD ACTIVITY / OTHER DEBITS — all amounts are debits
            if amount_values:
                withdrawals = amount_values[0]

        txn_type = self._classify_transaction(desc, section)
        date_str = self._resolve_date(raw_date, statement_month, statement_year)

        credit = deposits if deposits is not None else None
        debit = withdrawals if withdrawals is not None else None

        txn_obj = Transaction(
            date=date_str,
            description=desc,
            debit=debit,
            credit=credit,
        )
        transactions.append(txn_obj)

        raw_txns.append({
            "date": date_str,
            "description": desc,
            "credit": credit,
            "debit": debit,
            "transaction_type": txn_type,
            "section": section,
            "running_balance": None,
        })

    def _extract_customer_block(
        self, lines: List[str]
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        customer: Optional[str] = None
        co_customer: Optional[str] = None
        dba: Optional[str] = None

    # ── NEW: find the sequence-code anchor first ──────────────────────────
    # BancFirst puts the customer block immediately AFTER a line like
    # "3 *0009741" or "5 *0009551".  We locate that anchor so we don't
    # accidentally pick up boilerplate that appears BEFORE it.
        anchor_idx = None
        for i, line in enumerate(lines[:60]):
            if _SEQUENCE_CODE_RE.match(line.strip()):
                anchor_idx = i
                break          # take the FIRST match; there may be duplicates

    # If no anchor found, fall back to scanning from the top (old behaviour)
        scan_start = (anchor_idx + 1) if anchor_idx is not None else 0
        for line in lines[scan_start : scan_start + 20]:   # tight window after anchor
            stripped = line.strip()
            if not stripped:
                continue
            if _SEQUENCE_CODE_RE.match(stripped):           # another seq code line
                continue
            if _HEADER_BOILERPLATE_RE.match(stripped):      # "Dir 1 251 13", etc.
                continue
            if _ADDRESS_SKIP_RE.match(stripped):            # "PO BOX ...", zip lines
                break                                       # address = end of block
            if stripped.startswith("(") and stripped.endswith(")"):  # phone
                continue
            if re.match(r"^\d", stripped):                  # digit-leading line
                continue
            lower = stripped.lower()
            if any(b in lower for b in _CUSTOMER_BLOCKLIST):
                continue
            if len(stripped) < 4:
                continue

        # --- DBA line ---
            dba_match = _DBA_RE.match(stripped)
            if dba_match:
                if dba is None:
                    dba = dba_match.group(1).strip()
                break   # after DBA only address follows → stop
            if customer is None:
                customer = stripped
                continue

            if co_customer is None:
                co_customer = stripped
                continue

        # Both names filled and no DBA yet → next meaningful line is DBA or address
            break

        return customer, co_customer, dba
    def _parse_checks_row(self, line: str, statement_month: Optional[int], statement_year: Optional[int], transactions: List[Transaction], checks: List[Dict[str, Any]], raw_txns: List[Dict[str, Any]]):
        if self._should_skip_line(line):
            return
        
        # 3 groups of Date | Check No | Amount
        parts = re.findall(r"(\d{1,2}/\d{1,2})\s+([A-Za-z0-9-]+\*?)\s+([\d,]+\.\d{2}-?)", line)
        for date_raw, check_num, amount_raw in parts:
            date_str = self._resolve_date(date_raw, statement_month, statement_year)
            amount = self._parse_money(amount_raw)
            if amount is not None:
                is_non_seq = check_num.endswith("*")
                clean_check_num = check_num.rstrip("*")
                
                checks.append({
                    "date": date_str,
                    "check_number": clean_check_num,
                    "amount": amount,
                    "missing_sequence_flag": is_non_seq,
                })
                
                txn_obj = Transaction(
                    date=date_str,
                    description=f"Check {clean_check_num}",
                    debit=amount,
                    credit=None,
                )
                transactions.append(txn_obj)
                
                raw_txns.append({
                    "date": date_str,
                    "description": f"Check {clean_check_num}",
                    "credit": None,
                    "debit": amount,
                    "transaction_type": "check",
                    "section": "CHECKS",
                    "running_balance": None,
                })

    

    def _extract_account_number(self, text: str) -> Optional[str]:
        match = re.search(r"ACCOUNT\s+NUMBER\s*[\n\r]+.*?([0-9]{10})", text, re.IGNORECASE)
        if match:
            return match.group(1)
        # fallback
        match2 = re.search(r"(?<!-)\b([0-9]{10})\b(?!-)", text)
        if match2:
            return match2.group(1)
        return None

    def _extract_statement_date(self, text: str) -> Optional[str]:
        match = re.search(r"STATEMENT\s+DATE\s*[\n\r]+.*?(\d{1,2}/\d{1,2}/\d{2,4})", text, re.IGNORECASE)
        if match:
            return parse_date(match.group(1), statement_year=self.context.statement_year)
        return None

    def _extract_period(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        # Assume start date is missing or derive from transactions later. For now, try to find a date range.
        return None, None
        
    def _extract_beginning_balance(self, text: str) -> Optional[float]:
        match = re.search(r"Beginning\s+Balance\s+\d{1,2}/\d{1,2}/\d{2,4}\s+([\d,]+\.\d{2}-?)", text, re.IGNORECASE)
        if match:
            return self._parse_money(match.group(1))
        return None
        
    def _extract_ending_balance(self, text: str) -> Optional[float]:
        match = re.search(r"\*\*\s*Ending\s+Balance\s+\d{1,2}/\d{1,2}/\d{2,4}\s+([\d,]+\.\d{2}-?)\s*\*\*", text, re.IGNORECASE)
        if match:
            return self._parse_money(match.group(1))
        return None

    def _extract_count_total(self, text: str, label_regex: str) -> Tuple[Optional[int], Optional[float]]:
        match = re.search(rf"{label_regex}\s+(\d+)\s+([\d,]+\.\d{2}-?)", text, re.IGNORECASE)
        if match:
            return int(match.group(1)), self._parse_money(match.group(2))
        return None, None
        
    def _extract_labeled_amount(self, text: str, label: str) -> Optional[float]:
        match = re.search(rf"{re.escape(label)}\s+([\d,]+\.\d{2}-?)", text, re.IGNORECASE)
        if match:
            return self._parse_money(match.group(1))
        return None

    def _parse_money(self, raw: str) -> Optional[float]:
        if not raw:
            return None
        cleaned = raw.strip()
        negative = cleaned.endswith("-")
        cleaned = cleaned.rstrip("-").replace("$", "").replace(",", "").strip()
        try:
            value = float(cleaned)
            return -value if negative else value
        except ValueError:
            return None

    def _resolve_date(self, raw: str, statement_month: Optional[int], statement_year: Optional[int]) -> Optional[str]:
        if not statement_year:
            return parse_date(raw)
        
        try:
            m, d = raw.split("/")
            mm = int(m)
            dd = int(d)
            yyyy = statement_year
            if statement_month == 1 and mm > 1:
                yyyy -= 1
            return f"{yyyy:04d}-{mm:02d}-{dd:02d}"
        except:
            return parse_date(raw, statement_year=statement_year)

    def _is_image_caption(self, line: str) -> bool:
        lower = line.lower()
        if "number:" in lower and "date:" in lower and "amount:" in lower:
            return True
        if "deposit date:" in lower and "amount:" in lower:
            return True
        return False

    def _should_skip_line(self, line: str) -> bool:
        lower = line.lower()
        return any(re.search(pattern, lower) for pattern in _SKIP_PATTERNS)

    def _classify_transaction(self, description: str, section: str) -> str:
        upper = description.upper()
        if "BANKCARD" in upper and "DEP" in upper:
            return "card_deposit"
        if "BANKCARD" in upper and "DISC" in upper:
            return "card_discount_fee"
        if "INTERNET TRANSFER FROM" in upper:
            return "internal_transfer_in"
        if "INTERNET TRANSFER TO" in upper:
            return "internal_transfer_out"
        if "POS PURCHASE" in upper:
            return "pos_debit"
        if "OVERDRAFT CHARGE FOR" in upper:
            return "overdraft_fee"
        if "INSUFFICIENT CHARGE FOR" in upper:
            return "nsf_fee"
        if "SERVICE CHARGE" in upper:
            return "service_fee"
        if "ACHPAYMENT" in upper or "FINTECHEFT" in upper or "INST XFER" in upper or "CASH-ARC" in upper or "LSPD CAPITAL" in upper or "EBF HOLDINGS" in upper:
            return "ach_debit"
        if "TAX PMT" in upper:
            return "tax_payment"
        if upper == "DEPOSIT":
            return "cash_deposit"
        if "UTIL PAYMT" in upper or "OG&E" in upper or "ATT/PAYMENT" in upper:
            return "utility_payment"
        if "BUS INSUR" in upper:
            return "insurance_payment"
        if "REFUND INSUFFICIENT CHARGE" in upper:
            return "fee_refund"
            
        if section == "CHECKS":
            return "check"
            
        return "unknown"

    def _validate(self, metadata: StatementMetadata, transactions: List[Transaction]) -> List[str]:
        errors: List[str] = []
        credit_sum = round(sum(float(txn.credit or 0) for txn in transactions), 2)
        debit_sum = round(sum(float(txn.debit or 0) for txn in transactions), 2)
        
        if metadata.opening_balance is not None and metadata.closing_balance is not None:
            expected = round(metadata.opening_balance + credit_sum - debit_sum, 2)
            if abs(expected - metadata.closing_balance) > 0.05:
                errors.append(f"Balance chain failed: {metadata.opening_balance} + {credit_sum} - {debit_sum} = {expected}, expected {metadata.closing_balance}.")
                
        return errors

    def _text(self) -> str:
        if self.context.raw_text:
            return self.context.raw_text
        return "\n".join(self._lines())

    def _lines(self) -> List[str]:
        if self.context.raw_text:
            return [line.strip() for line in self.context.raw_text.splitlines() if line.strip()]
        return [" ".join(str(cell) for cell in row if str(cell).strip()).strip() for row in self.context.rows if row and any(str(cell).strip() for cell in row)]


register_parser("BANCFIRST", BancFirstParser)
register_parser("BANCFIRST_BANK", BancFirstParser)
register_template_parser("bancfirst_sectioned_activity_v1", BancFirstParser)