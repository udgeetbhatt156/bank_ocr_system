"""Lake Michigan Credit Union statement parser."""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from app.models.schemas import Transaction
from app.parsers.base import BaseParser
from app.parsers.registry import register_parser, register_template_parser
from app.parsers.result import ParseResult, StatementMetadata
from app.services.amount_utils import clean_amount
from app.services.date_utils import parse_date as parse_date_util
from app.services.postprocessor import calculate_confidence

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
    "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
    "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

def parse_date(raw: str, year: int = 2025) -> Optional[str]:
    raw = raw.strip()
    m = re.match(r"([A-Z][a-z]{2})\s+(\d{1,2})$", raw)
    if not m:
        return None
    month_num = MONTH_MAP.get(m.group(1))
    if not month_num:
        return None
    day = int(m.group(2))
    return f"{year}-{month_num:02d}-{day:02d}"

def parse_amount(raw: str) -> Tuple[Decimal, bool]:
    raw = raw.strip()
    is_negative = False

    if raw.startswith("(") and raw.endswith(")"):
        is_negative = True
        raw = raw[1:-1]

    if raw.startswith("-"):
        is_negative = True
        raw = raw[1:]

    raw = raw.replace("$", "").replace(",", "")
    try:
        return Decimal(raw), is_negative
    except InvalidOperation:
        return Decimal("0"), False

class LakeMichiganCreditUnionParser(BaseParser):
    """Parser for Lake Michigan Credit Union statements."""

    parser_id = "lake_michigan_credit_union"

    def extract_metadata(self) -> StatementMetadata:
        text = self._text()
        
        # Account Number Masked
        account_number = None
        m_acc = re.search(r"Account Number\s+(xxxxxx\d{4})", text, re.IGNORECASE)
        if m_acc:
            account_number = m_acc.group(1).strip()
            
        account_type = "BUSINESS ASCEND CHECKING"
        customer_name = ""
        m_cust = re.search(r"UNTIL SUCH TIME INC", text, re.IGNORECASE)
        if m_cust:
            customer_name = "UNTIL SUCH TIME INC"

        statement_start_date = None
        statement_end_date = None
        m_dates = re.search(r"(\d{1,2}/\d{1,2}/\d{4})\s*-\s*(\d{1,2}/\d{1,2}/\d{4})", text)
        if m_dates:
            statement_start_date = m_dates.group(1)
            statement_end_date = m_dates.group(2)
            
        opening_balance = None
        closing_balance = None
        total_credits = None
        total_debits = None

        # Look for Summary-Share Accounts table specifically for ID 01
        lines = text.split("\n")
        in_summary = False
        for line in lines:
            if "Summary-Share Accounts" in line:
                in_summary = True
            elif in_summary and "01" in line and "CHECKING" in line:
                parts = line.split()
                # Example: 01 UST CHECKING ($102.18) $4,909.79
                if len(parts) >= 4:
                    end_val, end_neg = parse_amount(parts[-1])
                    closing_balance = -float(end_val) if end_neg else float(end_val)
                    
                    beg_val, beg_neg = parse_amount(parts[-2])
                    opening_balance = -float(beg_val) if beg_neg else float(beg_val)
                in_summary = False
            elif in_summary and "Total" in line and len(line.split()) <= 2:
                # End of summary table
                in_summary = False

        m_dep = re.search(r"Total Deposits\s*\$([\d,]+\.\d{2})", text, re.IGNORECASE)
        if m_dep:
            total_credits = float(m_dep.group(1).replace(",", ""))

        m_deb = re.search(r"Total Withdrawals\s*\$([\d,]+\.\d{2})", text, re.IGNORECASE)
        if m_deb:
            total_debits = float(m_deb.group(1).replace(",", ""))
            
        return StatementMetadata(
            bank_id="LMCU",
            bank_name="Lake Michigan Credit Union",
            account_number=account_number,
            customer_name=customer_name,
            account_type=account_type,
            statement_end_date=statement_end_date,
            opening_balance=opening_balance,
            closing_balance=closing_balance,
            current_balance=closing_balance,
            total_credits=total_credits,
            total_debits=total_debits,
        )

    def extract_transactions(self) -> List[Transaction]:
        raw_transactions = []
        
        current_txn = None
        current_account_id = None
        
        def is_header_or_footer(text: str) -> bool:
            if "LAKE MICHIGAN CREDIT UNION" in text and "P.O. Box" in text: return True
            if "---continued on the following page---" in text: return True
            if "UNTIL SUCH TIME INC" in text and "Account Number" in text: return True
            if re.match(r"^Page \d+", text): return True
            if "Trans Eff Date Transaction Withdrawal Deposit Balance" in text: return True
            if "Total Deposits $" in text: return True
            if "Total Withdrawals $" in text: return True
            if "RETURN SERVICE REQUESTED" in text: return True
            if "Checking Account Summary" in text: return True
            if "Dividend Summary" in text: return True
            return False

        statement_year = 2025 # Default as per rules
        metadata = self.extract_metadata()
        if metadata.statement_end_date:
            m = re.search(r"(\d{4})", metadata.statement_end_date)
            if m:
                statement_year = int(m.group(1))

        # We will parse row by row from the text since pdfplumber might not split columns
        for page_info in self.context.rows_by_page() if hasattr(self.context, 'rows_by_page') else [(1, self.context.rows)]:
            rows = page_info[1]
            
            for row in rows:
                if not row:
                    continue
                
                row_str = " ".join(str(c).strip() for c in row if str(c).strip()).strip()
                row_str = re.sub(r"\s+", " ", row_str)
                
                # Check for account section headers
                m_acct = re.search(r"Share Account ID\s+(\d{2})", row_str, re.IGNORECASE)
                if m_acct:
                    current_account_id = m_acct.group(1)
                    if current_txn:
                        if current_account_id == "01": 
                            pass
                        raw_transactions.append(current_txn)
                        current_txn = None
                    continue
                
                # We only want to extract transactions for Account 01
                if current_account_id != "01":
                    continue
                    
                if is_header_or_footer(row_str) or not row_str:
                    continue
                
                # Extract amounts from the end of ANY line
                # Allow spacing inside the amount e.g. "$1, 887.15" -> \d[\d,\s]*\.\d{2}
                amount_pattern = r"(?:-\$|\$)\s*\d[\d,\s]*\.\d{2}|\(\s*\$\s*\d[\d,\s]*\.\d{2}\s*\)"
                amounts = []
                while True:
                    m_amt = re.search(r"(?:^|\s+)(" + amount_pattern + r")$", row_str)
                    if m_amt:
                        amt_str = m_amt.group(1).replace(" ", "")
                        amounts.insert(0, amt_str)
                        row_str = row_str[:m_amt.start()].strip()
                    else:
                        break
                        
                if not row_str and not amounts:
                    continue
                
                m_start = None
                if row_str:
                    m_start = re.match(r"^([A-Z][a-z]{2}\s+\d{1,2})(?:\s+(.*))?$", row_str)
                
                if m_start: # New Transaction
                    if current_txn:
                        raw_transactions.append(current_txn)
                        current_txn = None
                        
                    trans_date_str = m_start.group(1)
                    remainder = m_start.group(2) or ""
                    
                    if "Ending Balance" in remainder or "Beginning Balance" in remainder:
                        continue
                        
                    trans_date = parse_date(trans_date_str, year=statement_year)
                    
                    # Optional Eff Date
                    m_eff = re.match(r"^([A-Z][a-z]{2}\s+\d{1,2})\s+(.*)", remainder)
                    if m_eff:
                        remainder = m_eff.group(2) or ""
                        
                    current_txn = {
                        "date": trans_date,
                        "desc_parts": [remainder.strip()] if remainder.strip() else [],
                        "debit": None,
                        "credit": None,
                        "balance": None
                    }
                else:
                    # Continuation line
                    if current_txn and row_str:
                        current_txn["desc_parts"].append(row_str)
                        
                # Apply amounts to current_txn
                if amounts and current_txn:
                    withdrawal = None
                    deposit = None
                    balance = None
                    
                    if len(amounts) >= 2:
                        amt1, amt2 = amounts[-2], amounts[-1]
                        v1, neg1 = parse_amount(amt1)
                        if neg1:
                            withdrawal = float(v1)
                        else:
                            deposit = float(v1)
                            
                        v2, neg2 = parse_amount(amt2)
                        balance = -float(v2) if neg2 else float(v2)
                    elif len(amounts) == 1:
                        amt1 = amounts[0]
                        v1, neg1 = parse_amount(amt1)
                        desc_text = " ".join(current_txn["desc_parts"]).lower()
                        if "beginning balance" in desc_text or "ending balance" in desc_text:
                            balance = -float(v1) if neg1 else float(v1)
                        else:
                            if neg1:
                                withdrawal = float(v1)
                            else:
                                deposit = float(v1)
                                
                    if withdrawal is not None: current_txn["debit"] = withdrawal
                    if deposit is not None: current_txn["credit"] = deposit
                    if balance is not None: current_txn["balance"] = balance

        if current_txn:
            raw_transactions.append(current_txn)
            
        transactions: List[Transaction] = []
        for tx in raw_transactions:
            desc = " ".join(tx["desc_parts"]).strip()
            desc = re.sub(r"\s+", " ", desc)
            
            # Skip if it's just "Beginning Balance" or "Ending Balance"
            if desc.lower() in ("beginning balance", "ending balance"):
                continue
                
            transactions.append(Transaction(
                date=tx["date"],
                description=desc,
                debit=tx["debit"],
                credit=tx["credit"],
                balance=tx["balance"]
            ))
            
        return transactions

    def parse(self) -> ParseResult:
        metadata = self.extract_metadata()
        transactions = self.extract_transactions()
        
        validation_errors = []
        if metadata.opening_balance is not None and metadata.closing_balance is not None:
            expected_closing = round(
                metadata.opening_balance + (metadata.total_credits or 0) - (metadata.total_debits or 0),
                2
            )
            if abs(expected_closing - metadata.closing_balance) > 0.05:
                validation_errors.append(
                    f"Summary balance reconciliation failed: "
                    f"Start={metadata.opening_balance} + Credits={metadata.total_credits} - Debits={metadata.total_debits} "
                    f"= {expected_closing}, Expected End={metadata.closing_balance}"
                )
                
        structured_transactions = []
        for txn in transactions:
            is_debit = txn.debit is not None
            structured_transactions.append({
                "date": txn.date,
                "description": txn.description,
                "transaction_type": "debit" if is_debit else "credit",
                "amount": txn.debit if is_debit else txn.credit,
                "running_balance": txn.balance
            })
            
        structured_output = {
            "bank_name": "Lake Michigan Credit Union",
            "customer_name": metadata.customer_name,
            "account_number_masked": metadata.account_number,
            "statement_start_date": metadata.statement_start_date,
            "statement_end_date": metadata.statement_end_date,
            "previous_balance": metadata.opening_balance,
            "current_balance": metadata.closing_balance,
            "transactions": structured_transactions
        }

        return ParseResult(
            metadata=metadata,
            transactions=transactions,
            confidence=calculate_confidence([txn.dict() for txn in transactions]),
            parser_id=self.parser_id,
            bank_id=metadata.bank_id,
            template_id=self.context.template_id if hasattr(self.context, 'template_id') else None,
            validation_errors=validation_errors,
            extra={"lmcu_output": structured_output},
        )

    def _text(self) -> str:
        if hasattr(self.context, 'raw_text') and self.context.raw_text:
            return self.context.raw_text
        return "\\n".join(" ".join(str(cell) for cell in row if str(cell).strip()).strip() for row in self.context.rows if row and any(str(cell).strip() for cell in row))

register_parser("LMCU", LakeMichiganCreditUnionParser)
register_parser("LAKE_MICHIGAN_CREDIT_UNION", LakeMichiganCreditUnionParser)
register_template_parser("lake_michigan_credit_union", LakeMichiganCreditUnionParser)
