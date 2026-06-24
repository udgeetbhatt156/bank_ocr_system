"""Stellar Bank statement parser."""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.models.schemas import Transaction
from app.parsers.base import BaseParser
from app.parsers.registry import register_parser, register_template_parser
from app.parsers.result import ParseResult, StatementMetadata
from app.services.amount_utils import clean_amount
from app.services.date_utils import parse_date
from app.services.postprocessor import calculate_confidence

class StellarBankParser(BaseParser):
    """Parser for Stellar Bank statements."""

    parser_id = "stellar_bank"

    def extract_metadata(self) -> StatementMetadata:
        """Extract statement-level metadata from the context."""
        text = self._text()
        
        # Account Number Masked
        account_number = None
        m_acc = re.search(r"Acct Ending\s*(\d{4})", text, re.IGNORECASE)
        if m_acc:
            account_number = m_acc.group(1).strip()
            
        # Account Type
        account_type = "Checking Account"
        if re.search(r"Small Business Checking", text, re.IGNORECASE):
            account_type = "Small Business Checking"
        
        # Customer Name & Address
        # First text block on page 1, left-aligned, above "CHECKING ACCOUNT"
        customer_name = ""
        
        # Statement Dates
        # "Statement Dates 07/01/25 thru 07/31/25"
        statement_start_date = None
        statement_end_date = None
        m_dates = re.search(r"Statement Dates\s+(\d{2}/\d{2}/\d{2,4})\s+thru\s+(\d{2}/\d{2}/\d{2,4})", text, re.IGNORECASE)
        if m_dates:
            statement_start_date = parse_date(m_dates.group(1), statement_year=self.context.statement_year)
            statement_end_date = parse_date(m_dates.group(2), statement_year=self.context.statement_year)
            
        # Balances
        opening_balance = None
        closing_balance = None
        
        m_prev = re.search(r"Previous Balance\s+([\d,]+\.\d{2})", text, re.IGNORECASE)
        if m_prev:
            opening_balance = clean_amount(m_prev.group(1))
            
        m_end = re.search(r"Current Balance\s+([\d,]+\.\d{2})", text, re.IGNORECASE)
        if m_end:
            closing_balance = clean_amount(m_end.group(1))

        # Totals
        total_credits = None
        credit_count = None
        total_debits = None
        debit_count = None
        
        m_dep = re.search(r"Total Deposits\s*\(?(\d+)?\)?\s*\$?\s*([\d,]+\.\d{2})", text, re.IGNORECASE)
        if m_dep:
            if m_dep.group(1):
                credit_count = int(m_dep.group(1))
            total_credits = clean_amount(m_dep.group(2))

        m_deb = re.search(r"Total Withdrawals\s*\(?(\d+)?\)?\s*\$?\s*([\d,]+\.\d{2})", text, re.IGNORECASE)
        if m_deb:
            if m_deb.group(1):
                debit_count = int(m_deb.group(1))
            total_debits = clean_amount(m_deb.group(2))
            
        return StatementMetadata(
            bank_id="STELLAR_BANK",
            bank_name="Stellar Bank",
            account_number=account_number,
            customer_name=customer_name,
            account_type=account_type,
            statement_end_date=statement_end_date,
            opening_balance=opening_balance,
            closing_balance=closing_balance,
            current_balance=closing_balance,
            total_credits=total_credits,
            credit_count=credit_count,
            total_debits=total_debits,
            debit_count=debit_count,
        )

    def extract_transactions(self) -> List[Transaction]:
        """Extract transactions per section rules."""
        raw_transactions = []
        
        date_pattern = re.compile(r"^\d{1,2}/\d{1,2}$")
        current_txn = None
        current_section = None
        
        def is_header_or_footer(text: str) -> bool:
            text_upper = text.upper()
            if len(text) > 120: return True
            # Bank details
            if "STELLAR BANK" in text_upper: return True
            if "EQUAL HOUSING LENDER" in text_upper: return True
            if "MEMBER FDIC" in text_upper: return True
            if "HOUSTON TX" in text_upper: return True
            if "HOUSTON, TX" in text_upper: return True
            # Pagination
            if re.search(r"\bPAGE\s+\w+\b", text_upper): return True
            # Account summary headers
            if "PRIMARY ACCOUNT" in text_upper: return True
            if "ACCT ENDING" in text_upper: return True
            if "SMALL BUSINESS CHECKING" in text_upper: return True
            if "ENCLOSURES" in text_upper: return True
            if "DATE DESCRIPTION AMOUNT" in text_upper: return True
            # Disclosure keywords
            if "IN CASE OF ERRORS" in text_upper: return True
            if "TELEPHONE US" in text_upper: return True
            if "REGULATION E" in text_upper: return True
            if "THIS BALANCE SHOULD AGREE" in text_upper: return True
            if "STATEMENT SHOWN ON THIS BANK BALANCE" in text_upper: return True
            # Odd OCR artifacts seen in statements
            if "AUXILIARY CREDIT" in text_upper: return True
            if "REFERENCE DEPOSIT" in text_upper: return True
            return False
        
        for page_info in self.context.rows_by_page() if hasattr(self.context, 'rows_by_page') else [(1, self.context.rows)]:
            page_num = page_info[0]
            rows = page_info[1]
            
            for row in rows:
                if not row:
                    continue
                
                row_str = " ".join(str(c) for c in row if str(c).strip()).strip()
                row_str_upper = row_str.upper()
                
                # Section Identification
                if "DEPOSITS AND OTHER CREDITS" in row_str_upper:
                    current_section = "credit"
                    continue
                elif "CHECKS AND WITHDRAWALS" in row_str_upper:
                    current_section = "debit"
                    continue
                elif "CHECKS IN NUMBER ORDER" in row_str_upper:
                    current_section = "skip"
                    if current_txn:
                        raw_transactions.append(current_txn)
                    current_txn = None
                    continue
                elif "DAILY BALANCE INFORMATION" in row_str_upper:
                    current_section = "skip"
                    if current_txn:
                        raw_transactions.append(current_txn)
                    current_txn = None
                    continue
                elif "CHECKBOOK RECONCILIATION" in row_str_upper or "ELECTRONIC FUNDS TRANSFERS" in row_str_upper:
                    current_section = "skip"
                    if current_txn:
                        raw_transactions.append(current_txn)
                    current_txn = None
                    continue
                    
                if not current_section or current_section == "skip":
                    continue
                    
                if is_header_or_footer(row_str):
                    continue
                    
                first_cell = str(row[0]).strip()
                is_date = bool(date_pattern.match(first_cell))
                
                if is_date:
                    if current_txn:
                        raw_transactions.append(current_txn)
                        
                    date_str = parse_date(first_cell, statement_year=self.context.statement_year)
                    non_empty = [str(c).strip() for c in row[1:] if str(c).strip()]
                    
                    amount_candidate = None
                    desc_cells = []
                    
                    if non_empty:
                        last_val = non_empty[-1]
                        
                        # Debits have trailing minus in Stellar Bank statements
                        is_negative = False
                        if last_val.endswith('-'):
                            last_val = last_val[:-1]
                            is_negative = True
                            
                        parsed_amount = clean_amount(last_val)
                        if parsed_amount is not None:
                            amount_candidate = parsed_amount
                            desc_cells = non_empty[:-1]
                        else:
                            desc_cells = non_empty
                    
                    current_txn = {
                        "date": date_str,
                        "desc_parts": desc_cells,
                        "amount": amount_candidate,
                        "type": current_section,
                    }
                else:
                    # Continuation line
                    if current_txn:
                        non_empty = [str(c).strip() for c in row if str(c).strip()]
                        if non_empty:
                            last_val = non_empty[-1]
                            is_negative = False
                            if last_val.endswith('-'):
                                last_val_check = last_val[:-1]
                            else:
                                last_val_check = last_val
                                
                            parsed_amount = clean_amount(last_val_check)
                            
                            # If it's a continuation line but has an amount, it might be a weirdly formatted row, 
                            # but template says continuation line does NOT start with date and does NOT end with amount.
                            if parsed_amount is not None:
                                pass # This shouldn't be a continuation line if it has an amount, but we might merge it anyway if it missed date
                            
                            current_txn["desc_parts"].extend(non_empty)

        if current_txn:
            raw_transactions.append(current_txn)
            
        # Classify and process transactions
        transactions: List[Transaction] = []
        
        # Build running balance
        running_balance = 0.0 # Will be populated in parse() or here if we have metadata
        
        for tx in raw_transactions:
            desc = " | ".join(tx["desc_parts"]).strip()
            desc = re.sub(r"\s+", " ", desc)
            
            debit = None
            credit = None
            
            if tx["amount"] is not None:
                if tx["type"] == "credit":
                    credit = tx["amount"]
                else:
                    debit = tx["amount"]
                    
            transactions.append(Transaction(
                date=tx["date"],
                description=desc,
                debit=debit,
                credit=credit,
                balance=None # Balance reconciliation happens later or is computed
            ))
            
        return transactions

    def parse(self) -> ParseResult:
        """Parse statement and return result."""
        metadata = self.extract_metadata()
        transactions = self.extract_transactions()
        
        # Balance reconciliation as per rule 5
        if metadata.opening_balance is not None:
            balance = metadata.opening_balance
            
            # Group by date
            by_date = {}
            for t in transactions:
                by_date.setdefault(t.date, []).append(t)
                
            for d in sorted(by_date.keys()):
                day_txns = by_date[d]
                # Apply credits before debits
                day_txns.sort(key=lambda t: t.debit is not None)
                for t in day_txns:
                    if t.credit is not None:
                        balance += t.credit
                    elif t.debit is not None:
                        balance -= t.debit
                    t.balance = round(balance, 2)
        
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
                
        credit_sum = round(sum(float(txn.credit or 0) for txn in transactions), 2)
        debit_sum = round(sum(float(txn.debit or 0) for txn in transactions), 2)
        credit_count = sum(1 for txn in transactions if txn.credit is not None)
        debit_count = sum(1 for txn in transactions if txn.debit is not None)

        if metadata.credit_count and metadata.credit_count != credit_count:
            validation_errors.append(f"Credit count mismatch: extracted {credit_count}, statement says {metadata.credit_count}.")
        if metadata.debit_count and metadata.debit_count != debit_count:
            validation_errors.append(f"Debit count mismatch: extracted {debit_count}, statement says {metadata.debit_count}.")
        if metadata.total_credits is not None and abs(credit_sum - metadata.total_credits) > 0.05:
            validation_errors.append(f"Credit total mismatch: extracted {credit_sum}, statement says {metadata.total_credits}.")
        if metadata.total_debits is not None and abs(debit_sum - metadata.total_debits) > 0.05:
            validation_errors.append(f"Debit total mismatch: extracted {debit_sum}, statement says {metadata.total_debits}.")

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
            "bank_name": "Stellar Bank",
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
            extra={"stellar_output": structured_output},
        )

    def _text(self) -> str:
        if hasattr(self.context, 'raw_text') and self.context.raw_text:
            return self.context.raw_text
        return "\\n".join(" ".join(str(cell) for cell in row if str(cell).strip()).strip() for row in self.context.rows if row and any(str(cell).strip() for cell in row))

register_parser("STELLAR", StellarBankParser)
register_parser("STELLAR_BANK", StellarBankParser)
register_template_parser("stellar_bank", StellarBankParser)
