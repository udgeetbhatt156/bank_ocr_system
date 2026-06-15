"""Indiana Members Credit Union (IMCU) statement parser."""

import re
from typing import Any, Dict, List, Optional, Tuple

from app.models.schemas import Transaction
from app.parsers.base import BaseParser
from app.parsers.registry import register_parser, register_template_parser
from app.parsers.result import ParseResult, StatementMetadata
from app.services.amount_utils import clean_amount
from app.services.date_utils import parse_date
from app.services.postprocessor import calculate_confidence

# SKIP regex to filter out page headers, marketing blocks, summaries
_SKIP_RE = re.compile(
    r"Statement of Account|"
    r"800\.556\.9268\s*\|\s*imcu\.com|"
    r"Member Number|"
    r"Statement For|"
    r"P\.O\.\s*Box\s*47769|"
    r"Page\s+\d+\s+of\s+\d+|"
    r"Continued from previous page\.|"
    r"RETURN SERVICE REQUESTED|"
    r"^\d{6}\s+\d+|\bCLT\b|"
    r"^\d{9}\s+\d|"
    r"Your IMCU Mastercard|"
    r"upgraded to a Visa|"
    r"New Digital Banking|"
    r"Check out IMCU\.COM|"
    r"more details\.|"
    r"Your Account Balances as of|"
    r"Need a Loan\?|"
    r"Call 800\.556\.9268|"
    r"www\.imcu\.com|"
    r"Account Balance Total|"
    r"Total Dividends Paid|"
    r"Beginning Balance|"
    r"Total Deposits for|"
    r"Total Withdrawals for|"
    r"Annual Percentage Yield|"
    r"Ending Balance|"
    r"Date\s+Transaction\s+Description|"
    r"Fees Paid|"
    r"Description\s+Current\s+YTD|"
    r"Acct-\d{4}\s+Total|"
    r"Summary by Check Number|"
    r"Asterisk next to number|"
    r"Number\s+Cleared\s+Amount|"
    r"INCASEOFERRORS|"
    r"MORTGAGEDISCLOSURE|"
    r"OPEN-ENDLOAN|"
    r"We appreciate your membership",
    re.IGNORECASE
)

_CUSTOMER_BLOCK_RE = re.compile(
    r"MIM LANDSCAPE DIVISION LLC|"
    r"3480 N STATE ROAD 267|"
    r"BROWNSBURG IN 46112",
    re.IGNORECASE
)

# Detect sub-account sections
_SECTION_HEADER_RE = re.compile(
    r"([A-Z\s]+)\s+ID\s+(\d{4})",
    re.IGNORECASE
)

# Detect standalone amount rows that shouldn't be appended to descriptions
_AMOUNT_ONLY_RE = re.compile(
    r"^[-+$]?[\d,]+\.\d{2}-?$",
    re.IGNORECASE
)


class IndianaMembersCUParser(BaseParser):
    """Parser for Indiana Members Credit Union statements."""

    parser_id = "indiana_members_cu"

    def extract_metadata(self) -> StatementMetadata:
        """Extract statement-level metadata from the context."""
        text = self._text()
        lines = self._lines()

        # Extract Member Number (Account Number)
        member_number = None
        member_match = re.search(r"Member\s+Number\s+(\S+)", text, re.IGNORECASE)
        if member_match:
            member_number = member_match.group(1).strip()

        # Customer name & address
        customer_name = "MIM LANDSCAPE DIVISION LLC"
        customer_address = "3480 N STATE ROAD 267 BROWNSBURG IN 46112"

        # Period dates
        start_date = None
        end_date = None
        period_match = re.search(
            r"Statement\s+For\s+(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})",
            text,
            re.IGNORECASE
        )
        if period_match:
            start_date = parse_date(period_match.group(1), statement_year=self.context.statement_year)
            end_date = parse_date(period_match.group(2), statement_year=self.context.statement_year)

        # Parse all accounts to get summary sums
        accounts_data = self._parse_sub_accounts()

        total_opening = 0.0
        total_closing = 0.0
        total_credits = 0.0
        total_debits = 0.0
        credit_count = 0
        debit_count = 0

        for acct_id, data in accounts_data.items():
            txns = data["transactions"]
            # Summarize opening/ending balance
            total_opening += data["opening_balance"]
            total_closing += data["ending_balance"]
            
            # Summarize transactions
            for txn in txns:
                if txn.credit is not None:
                    total_credits += txn.credit
                    credit_count += 1
                if txn.debit is not None:
                    total_debits += txn.debit
                    debit_count += 1

        return StatementMetadata(
            bank_id="IMCU",
            bank_name="Indiana Members Credit Union",
            account_number=member_number,
            account_holder=customer_name,
            customer_name=customer_name,
            customer_address=customer_address,
            statement_start_date=start_date,
            statement_end_date=end_date,
            opening_balance=round(total_opening, 2) if accounts_data else None,
            closing_balance=round(total_closing, 2) if accounts_data else None,
            current_balance=round(total_closing, 2) if accounts_data else None,
            total_credits=round(total_credits, 2),
            credit_count=credit_count,
            total_debits=round(total_debits, 2),
            debit_count=debit_count,
        )

    def extract_transactions(self) -> List[Transaction]:
        """Extract transactions from all sub-accounts with duplicate prevention."""
        all_txns: List[Transaction] = []
        accounts_data = self._parse_sub_accounts()
        
        seen_txns = {}
        for acct_id in sorted(accounts_data.keys()):
            for txn in accounts_data[acct_id]["transactions"]:
                # Create a key to identify identical transactions on the same day.
                # In postprocessing, descriptions are truncated to 100 chars, so we truncate here too.
                key = (
                    txn.date,
                    round(txn.debit, 2) if txn.debit is not None else None,
                    round(txn.credit, 2) if txn.credit is not None else None,
                    txn.description.strip().lower()[:90]
                )
                if key in seen_txns:
                    seen_txns[key] += 1
                    # Prepend unique prefix to bypass postprocessor 100-character truncation deduplication
                    txn.description = f"[#{seen_txns[key]}] {txn.description}"
                else:
                    seen_txns[key] = 1
                
                all_txns.append(txn)
                
        return all_txns

    def parse(self) -> ParseResult:
        """Parse the complete statement and return results."""
        metadata = self.extract_metadata()
        transactions = self.extract_transactions()
        
        # Balance chain validation
        validation_errors = []
        accounts_data = self._parse_sub_accounts()
        for acct_id, data in accounts_data.items():
            opening = data["opening_balance"]
            ending = data["ending_balance"]
            credits_sum = sum(t.credit for t in data["transactions"] if t.credit is not None)
            debits_sum = sum(t.debit for t in data["transactions"] if t.debit is not None)
            expected = round(opening + credits_sum - debits_sum, 2)
            if abs(expected - ending) > 0.05:
                validation_errors.append(
                    f"Account {acct_id} balance chain mismatch: "
                    f"Start={opening} + Credits={credits_sum:.2f} - Debits={debits_sum:.2f} "
                    f"= {expected:.2f}, Expected End={ending}"
                )

        # Build structured output
        raw_txns = []
        for idx, txn in enumerate(transactions, start=1):
            is_debit = txn.debit is not None
            raw_txns.append({
                "seq": idx,
                "date": txn.date,
                "description_full": txn.description,
                "transaction_type": "DEBIT" if is_debit else "CREDIT",
                "amount": txn.debit if is_debit else txn.credit,
                "direction": "DR" if is_debit else "CR",
                "running_balance": txn.balance,
                "category": self._classify_transaction_type(txn.description),
            })

        structured_output = {
            "bank_name": "Indiana Members Credit Union",
            "account_number": metadata.account_number,
            "customer_name": metadata.customer_name,
            "statement_period_start": metadata.statement_start_date,
            "statement_period_end": metadata.statement_end_date,
            "beginning_balance": metadata.opening_balance,
            "ending_balance": metadata.closing_balance,
            "total_credits": metadata.total_credits,
            "total_debits": metadata.total_debits,
            "deposit_count": metadata.credit_count,
            "debit_count": metadata.debit_count,
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
            validation_errors=validation_errors,
            extra={"indiana_members_cu_output": structured_output},
        )

    def _text(self) -> str:
        if self.context.raw_text:
            return self.context.raw_text
        return "\n".join(self._lines())

    def _lines(self) -> List[str]:
        if self.context.raw_text:
            return [line.strip() for line in self.context.raw_text.splitlines() if line.strip()]
        return [" ".join(str(cell) for cell in row if str(cell).strip()).strip() for row in self.context.rows if row and any(str(cell).strip() for cell in row)]

    def _classify_transaction_type(self, description: str) -> str:
        upper = description.upper()
        if "ACH" in upper or "DIRECT DEP" in upper or "PAYROLL" in upper:
            return "ach"
        if "DEBIT CARD" in upper or "PURCHASE" in upper:
            return "debit_card"
        if "ATM" in upper:
            return "atm"
        if "TRANSFER" in upper:
            return "internal_transfer"
        if "CHECK" in upper:
            return "check"
        return "other"

    def _extract_transaction_data(self, row: List[str]) -> Optional[Dict[str, Any]]:
        """Attempt to extract transaction values from a single row."""
        if not row:
            return None

        # Check for date MM/DD in the first or second column
        date = None
        desc = ""
        rest_of_row = []

        date_match = re.match(r"^(\d{2}/\d{2})\b", str(row[0]))
        if date_match:
            date = date_match.group(1)
            if len(str(row[0])) > 5:
                desc = str(row[0])[date_match.end():].strip()
                rest_of_row = row[1:]
            else:
                desc = str(row[1]) if len(row) > 1 else ""
                rest_of_row = row[2:]
        elif len(row) > 1:
            date_match = re.match(r"^(\d{2}/\d{2})\b", str(row[1]))
            if date_match:
                date = date_match.group(1)
                desc = str(row[1])[date_match.end():].strip()
                rest_of_row = row[2:]

        if not date:
            return None

        numeric_parts = [str(c).strip() for c in rest_of_row if str(c).strip()]

        debit = None
        credit = None
        balance = None

        if len(numeric_parts) == 2:
            part1 = numeric_parts[0]
            part2 = numeric_parts[1]

            if part1.endswith("-"):
                val = clean_amount(part1.replace("-", ""))
                if val is not None:
                    debit = abs(val)
            else:
                val = clean_amount(part1)
                if val is not None:
                    credit = abs(val)

            val_bal = clean_amount(part2.replace("-", ""))
            if val_bal is not None:
                balance = abs(val_bal)

        elif len(numeric_parts) == 3:
            part1 = numeric_parts[0]
            part2 = numeric_parts[1]
            part3 = numeric_parts[2]

            if part1 == "-" or not part1:
                val = clean_amount(part2)
                if val is not None:
                    credit = abs(val)
            else:
                val = clean_amount(part1.replace("-", ""))
                if val is not None:
                    debit = abs(val)

            val_bal = clean_amount(part3.replace("-", ""))
            if val_bal is not None:
                balance = abs(val_bal)

        if debit is None and credit is None:
            return None

        year = self.context.statement_year or 2025
        return {
            "date": f"{year}-{date[:2]}-{date[3:5]}",
            "description": desc,
            "debit": debit,
            "credit": credit,
            "balance": balance
        }

    def _parse_sub_accounts(self) -> Dict[str, Dict[str, Any]]:
        """Parse rows grouped by sub-account sections."""
        accounts = {}
        current_account = None
        active_txn = None
        in_checks_summary = False

        def find_amount_in_row(r_str: str) -> Optional[float]:
            m = re.search(r"\$?([\d,]+\.\d{2})-?", r_str)
            if m:
                return abs(clean_amount(m.group(1)))
            return None

        for idx, row in enumerate(self.context.rows):
            if not row:
                continue

            row_str = " ".join(str(c) for c in row).strip()
            if not row_str:
                continue

            # Skip standalone balance/amount artifact rows (unless we need them for adjacent balance lookup)
            if _AMOUNT_ONLY_RE.match(row_str):
                continue

            # Account section header detection
            header_match = _SECTION_HEADER_RE.search(row_str)
            if header_match:
                if active_txn and current_account:
                    accounts[current_account]["transactions"].append(
                        Transaction(**active_txn)
                    )
                    active_txn = None
                
                current_account = header_match.group(2)
                in_checks_summary = False
                
                if current_account not in accounts:
                    accounts[current_account] = {
                        "name": header_match.group(1).strip(),
                        "opening_balance": 0.0,
                        "ending_balance": 0.0,
                        "transactions": []
                    }
                
                # Check for balances within header row or adjacent rows
                if "Beginning Balance" in row_str:
                    m = re.search(r"Beginning\s+Balance\s+\$?([\d,]+\.\d{2})-?", row_str, re.IGNORECASE)
                    if m:
                        accounts[current_account]["opening_balance"] = abs(clean_amount(m.group(1)))
                    else:
                        # Check previous row
                        if idx > 0:
                            prev_str = " ".join(str(c) for c in self.context.rows[idx - 1]).strip()
                            amt = find_amount_in_row(prev_str)
                            if amt is not None:
                                accounts[current_account]["opening_balance"] = amt
                continue

            if current_account is None:
                continue

            # Update balances if they appear in summary rows
            if "Beginning Balance" in row_str:
                m = re.search(r"Beginning\s+Balance\s+\$?([\d,]+\.\d{2})-?", row_str, re.IGNORECASE)
                if m:
                    accounts[current_account]["opening_balance"] = abs(clean_amount(m.group(1)))
                else:
                    # Check previous row
                    if idx > 0:
                        prev_str = " ".join(str(c) for c in self.context.rows[idx - 1]).strip()
                        amt = find_amount_in_row(prev_str)
                        if amt is not None:
                            accounts[current_account]["opening_balance"] = amt
            if "Ending Balance" in row_str:
                m = re.search(r"Ending\s+Balance\s+\$?([\d,]+\.\d{2})-?", row_str, re.IGNORECASE)
                if m:
                    accounts[current_account]["ending_balance"] = abs(clean_amount(m.group(1)))
                else:
                    # Check previous row
                    if idx > 0:
                        prev_str = " ".join(str(c) for c in self.context.rows[idx - 1]).strip()
                        amt = find_amount_in_row(prev_str)
                        if amt is not None:
                            accounts[current_account]["ending_balance"] = amt

            # Handle Check register skip
            if "Summary by Check Number" in row_str or "Asterisk next to number" in row_str:
                in_checks_summary = True

            if in_checks_summary:
                continue

            # Check if this row is a new transaction
            txn_data = self._extract_transaction_data(row)
            if txn_data:
                if active_txn:
                    accounts[current_account]["transactions"].append(
                        Transaction(**active_txn)
                    )
                    active_txn = None
                active_txn = txn_data
                continue

            # Check skip patterns
            if _SKIP_RE.search(row_str) or _CUSTOMER_BLOCK_RE.search(row_str):
                continue

            # Handle description continuation
            if active_txn and row_str:
                if re.match(r"^\d{4}\s+", row_str) or "Checks Cleared" in row_str:
                    continue
                active_txn["description"] += " " + row_str

        # Append last active txn
        if active_txn and current_account:
            accounts[current_account]["transactions"].append(
                Transaction(**active_txn)
            )

        return accounts


register_parser("IMCU", IndianaMembersCUParser)
register_parser("INDIANA_MEMBERS_CREDIT_UNION", IndianaMembersCUParser)
register_template_parser("indiana_members_cu_v1", IndianaMembersCUParser)
