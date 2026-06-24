"""Exchange Bank statement parser."""

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

# Regex from the MD file
_STMT_DATE_RE = re.compile(r'Date\s+(\d{1,2}/\d{2}/\d{2})\s+Page\s+(\d+)\s+of\s+(\d+)', re.IGNORECASE)
_ACCT_ENDING_RE = re.compile(r'Account\s+Number\s+Ending\s+(\d{4})', re.IGNORECASE)
_IMAGES_RE = re.compile(r'Images\s+(\d+)', re.IGNORECASE)

_CUSTOMER_BLOCK_RE = re.compile(
    r'(?P<company>[A-Z0-9 ]+(?:LLC|INC|CORP))\s*\n'
    r'(?:DBA\s+(?P<dba>[A-Z0-9 &]+)\s*\n)?'
    r'(?P<address>[0-9]+[A-Z0-9 ]+)\s*\n'
    r'(?P<city>[A-Z ]+)\s+(?P<state>[A-Z]{2})\s+(?P<zip>\d{5})',
    re.MULTILINE
)

_ACCT_TYPE_RE = re.compile(r'(COMM\s+CKG\s+ANALYSIS\s+HR)', re.IGNORECASE)
_STMT_DATES_RE = re.compile(r'Statement\s+Dates\s+(\d{1,2}/\d{2}/\d{2})\s+thru\s+(\d{1,2}/\d{2}/\d{2})', re.IGNORECASE)
_PREV_BAL_RE = re.compile(r'Previous\s+Balance\s+([\d,]+\.\d{2})([-]?)', re.IGNORECASE)
_DEPOSITS_SUMMARY_RE = re.compile(r'(\d+)\s+Deposits/Credits\s+([\d,]+\.\d{2})', re.IGNORECASE)
_DEBITS_SUMMARY_RE = re.compile(r'(\d+)\s+Checks/Debits\s+([\d,]+\.\d{2})', re.IGNORECASE)
_SVC_CHARGE_RE = re.compile(r'Service\s+Charge\s+([\d,]+\.\d{2})', re.IGNORECASE)
_INTEREST_RE = re.compile(r'Interest\s+Paid\s+([\d,]+\.\d{2})', re.IGNORECASE)
_ENDING_BAL_RE = re.compile(r'Ending\s+Balance\s+([\d,]+\.\d{2})([-]?)', re.IGNORECASE)

_OD_FEE_TABLE_RE = re.compile(r'Total\s+Overdraft\s+Fees\s+\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})', re.IGNORECASE)
_RTN_FEE_TABLE_RE = re.compile(r'Total\s+Return\s+Item\s+Fees\s+\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})', re.IGNORECASE)

_DEPOSITS_SECTION_RE = re.compile(r'\*{4}DEPOSITSANDCREDITS\*{4}', re.IGNORECASE)
_WITHDRAWALS_SECTION_RE = re.compile(r'\*{4}WITHDRAWALSANDCHARGES\*{4}', re.IGNORECASE)
_CHECK_SUMMARY_SECTION_RE = re.compile(r'\*{4}SUMMARYBYCHECKNUMBER\*{4}', re.IGNORECASE)
_DAILY_BAL_SECTION_RE = re.compile(r'\*{4}DAILYBALANCESECTION\*{4}', re.IGNORECASE)
_COL_HEADER_RE = re.compile(r'^Date\s+Description\s+Amount\s*$', re.IGNORECASE | re.MULTILINE)

_SIMPLE_TXN_RE = re.compile(r'^(\d{1,2}/\d{2})\s+(.+?)\s+([\d,]+\.\d{2})\s*$', re.MULTILINE)
_ACH_LINE1_RE = re.compile(r'^(\d{1,2}/\d{2})\s+(.+?)\s+([\d,]+\.\d{2})\s*$', re.MULTILINE)
_ACH_LINE2_RE = re.compile(r'^\s*([A-Z0-9]+)\s+(\d{2}/\d{2}/\d{2})\s*$', re.MULTILINE)
_ACH_ID_RE = re.compile(r'^\s+ID\s+[#]?[-]?\s*([A-Z0-9\-]+)\s*$', re.MULTILINE | re.IGNORECASE)
_ACH_TRACE_RE = re.compile(r'^\s+TRACE\s+[#]?[-]?\s*(\d+)\s*$', re.MULTILINE | re.IGNORECASE)
_ACH_NAME_LINE_RE = re.compile(r'^\s{6,}([A-Z][A-Z0-9 &/]+)\s*$', re.MULTILINE)

_POS_LINE1_RE = re.compile(r'^(\d{1,2}/\d{2})\s+POSDEB\d+(\d{2}/\d{2}/\d{2})(\d+)\s+([\d,]+\.\d{2})\s*$', re.MULTILINE | re.IGNORECASE)
_POS_MERCHANT_RE = re.compile(r'^\s*([A-Z0-9#* ]+)\s*$', re.MULTILINE)

_SVC_CHARGE_BLOCK_RE = re.compile(
    r'(\d{1,2}/\d{2})\s+SERVICE\s+CHARGE\s+([\d,]+\.\d{2})\s*\n'
    r'(?:\s+SERVICE\s+CHARGE\s+([\d,]+\.\d{2}[-]?)\s*\n)?'
    r'(?:\s+DEBIT\s+ITEM\s+FEE\s+([\d,.]+[-]?)\s*\n)?'
    r'(?:\s+CR\s+ITEM\s+FEES\s+IN\s+S/C\s+([\d,.]+[-]?)\s*\n)?'
    r'(?:\s+TRANSIT\s+FEE\s+IN\s+S/C\s+([\d,.]+[-]?)\s*\n)?',
    re.IGNORECASE
)

_CHECK_ROW_RE = re.compile(r'(\d{1,2}/\d{2})\s+(\d{4}[*]?)\s+([\d,]+\.\d{2})', re.MULTILINE)
_CHECK_SKIP_NOTE_RE = re.compile(r'\*Indicates\s+Skip\s+in\s+Check\s+Number', re.IGNORECASE)
_DAILY_BAL_ROW_RE = re.compile(r'(\d{1,2}/\d{2})\s+([\d,]*\.\d{2}[-]?)', re.MULTILINE)

_DEPOSIT_IMAGE_RE = re.compile(r'DDA\s+REGULAR\s+DEPOSIT\s+Date:\s+(\d{2}/\d{2}/\d{2})\s+Amount:\s+\$([\d,]+\.\d{2})', re.IGNORECASE)
_CHECK_IMAGE_RE = re.compile(r'(?:DDA\s+FORCE\s+PAY\s+DEBIT|CHECK\s+#\s*\d+)\s+Date:\s+(\d{2}/\d{2}/\d{2})\s+Amount:\s+\$([\d,]+\.\d{2})', re.IGNORECASE)

_MICR_RE = re.compile(r'[*⑆]?(\d{4})[*⑆]\s+[*⑆](\d{9,10})[*⑆]\s+(\d{9})[*⑆]', re.MULTILINE)
_CONTINUATION_HEADER_RE = re.compile(r'COMM\s+CKG\s+ANALYSIS\s+HR\s+Ending\s+(\d{4})\s+\(Continued\)', re.IGNORECASE)

_SKIP_PATTERNS = [
    re.compile(r'COMM\s+CKG\s+ANALYSIS\s+HR', re.IGNORECASE),
    re.compile(r'Ending\s+\d{4}\s+\(Continued\)', re.IGNORECASE),
    re.compile(r'Date\s+Description\s+Amount', re.IGNORECASE),
    re.compile(r'NOTICE:\s+SEE\s+REVERSE\s+SIDE', re.IGNORECASE),
    re.compile(r'Date\s+\d{1,2}/\d{2}/\d{2}\s+Page\s+\d+', re.IGNORECASE),
    re.compile(r'Account\s+Number\s+Ending', re.IGNORECASE),
    re.compile(r'Images\s+\d+', re.IGNORECASE),
    re.compile(r'\*{4}\s+(DEPOSITS|WITHDRAWALS|SUMMARY|DAILY)', re.IGNORECASE),
    re.compile(r'Notice\s+of\s+Funds\s+Availab', re.IGNORECASE),
    re.compile(r'Pursuant\s+to\s+Regulation', re.IGNORECASE),
    re.compile(r'\*\s*\*\s*\*\s+Thank\s+You', re.IGNORECASE),
    re.compile(r'\*Indicates\s+Skip', re.IGNORECASE),
    re.compile(r'SUBSTITUTE\s+IMAGE\s+/\s+VIRTUAL\s+DOCUMENT', re.IGNORECASE),
]

def parse_amount(raw: str, is_debit_section: bool = False) -> float:
    raw = raw.strip().replace(',', '').replace('$', '')
    negative = raw.endswith('-')
    raw = raw.rstrip('-').strip()
    value = float(raw) if raw and raw != '.' else 0.0
    if negative or is_debit_section:
        value = -abs(value)
    return value

class ExchangeBankParser(BaseParser):
    parser_id = "exchange_bank"
    
    def _text(self) -> str:
        lines = []
        for row in self.context.rows:
            if not row: continue
            cleaned_cells = []
            for cell in row:
                c = str(cell).strip()
                # fix dates
                c = re.sub(r'(\d)\s+/\s+(\d)\s+(\d)', r'\1/\2\3', c)
                c = re.sub(r'(\d)\s+/\s+(\d)', r'\1/\2', c)
                # squash all spaces
                c = c.replace(' ', '')
                if c:
                    cleaned_cells.append(c)
            if cleaned_cells:
                lines.append(" ".join(cleaned_cells))  # single space between columns is fine because of .+?
        
        # Also append the raw_text at the end to ensure metadata that isn't in tables is available
        if hasattr(self.context, 'raw_text') and self.context.raw_text:
            lines.append("--- RAW TEXT START ---")
            lines.append(self.context.raw_text)
            
        return "\\n".join(lines)
    
    def extract_metadata(self) -> StatementMetadata:
        text_for_metadata = self.context.raw_text if hasattr(self.context, 'raw_text') and self.context.raw_text else self._text()
        
        # Calculate Confidence
        score = 0
        text_upper = text_for_metadata.upper()
        text_nospace = text_upper.replace(' ', '')
        
        if "EXCHANGEBANK" in text_nospace: score += 25
        if "COMMCKGANALYSISHR" in text_nospace: score += 20
        if "DEPOSITSANDCREDITS" in text_nospace: score += 20
        if "MILLEDGEVILLE" in text_nospace[:500] or "GEORGIA" in text_nospace[:500]: score += 15
        if "DEPOSIT" in text_nospace and "MERCHANTBANKCD" in text_nospace: score += 10
        if "DDAREGULARDEPOSIT" in text_nospace: score += 10
        
        template_id = "exchange_bank_comm_ckg" # force it for testing

        # Fields
        bank_name = "Exchange Bank"
        account_type = "COMM CKG ANALYSIS HR"
        account_number = None
        statement_start_date = None
        statement_end_date = None
        opening_balance = None
        closing_balance = None
        total_credits = None
        total_debits = None
        
        # Customer
        customer_name = None
        customer_address = None
        
        m_cust = _CUSTOMER_BLOCK_RE.search(text_for_metadata)
        if m_cust:
            customer_name = m_cust.group("company").strip()
            if m_cust.group("dba"):
                customer_name += " DBA " + m_cust.group("dba").strip()
            city_state_zip = f"{m_cust.group('city').strip()} {m_cust.group('state').strip()} {m_cust.group('zip').strip()}"
            customer_address = f"{m_cust.group('address').strip()}, {city_state_zip}"

        m_acct = _ACCT_ENDING_RE.search(text_for_metadata)
        if m_acct:
            account_number = m_acct.group(1).strip()
            
        m_dates = _STMT_DATES_RE.search(text_for_metadata)
        if m_dates:
            statement_start_date = parse_date(m_dates.group(1))
            statement_end_date = parse_date(m_dates.group(2))
            
        m_prev = _PREV_BAL_RE.search(text_for_metadata)
        if m_prev:
            opening_balance = parse_amount(m_prev.group(1) + m_prev.group(2))
            
        m_end = _ENDING_BAL_RE.search(text_for_metadata)
        if m_end:
            closing_balance = parse_amount(m_end.group(1) + m_end.group(2))
            
        m_dep = _DEPOSITS_SUMMARY_RE.search(text_for_metadata)
        if m_dep:
            total_credits = parse_amount(m_dep.group(2))
            
        m_deb = _DEBITS_SUMMARY_RE.search(text_for_metadata)
        if m_deb:
            total_debits = parse_amount(m_deb.group(2))
            
        # Overdraft and return items fees
        od_fee_period = None
        od_fee_ytd = None
        rtn_fee_period = None
        rtn_fee_ytd = None
        
        m_od = _OD_FEE_TABLE_RE.search(text_for_metadata)
        if m_od:
            od_fee_period = parse_amount(m_od.group(1))
            od_fee_ytd = parse_amount(m_od.group(2))
            
        m_rtn = _RTN_FEE_TABLE_RE.search(text_for_metadata)
        if m_rtn:
            rtn_fee_period = parse_amount(m_rtn.group(1))
            rtn_fee_ytd = parse_amount(m_rtn.group(2))

        return StatementMetadata(
            bank_id="EXCHANGE_BANK",
            bank_name=bank_name,
            account_number=account_number,
            account_type=account_type,
            statement_start_date=statement_start_date,
            statement_end_date=statement_end_date,
            opening_balance=opening_balance,
            closing_balance=closing_balance,
            current_balance=closing_balance,
            total_credits=total_credits,
            total_debits=total_debits,
            customer_name=customer_name,
            customer_address=customer_address,
        )

    def extract_transactions(self) -> List[Transaction]:
        text = self._text()
        transactions: List[Transaction] = []
        
        # 1. Parse checks from check summary section
        check_summary_matches = _CHECK_ROW_RE.finditer(text)
        for m in check_summary_matches:
            date_str = m.group(1)
            check_num = m.group(2).replace('*', '')
            amount = parse_amount(m.group(3), is_debit_section=True)
            transactions.append(Transaction(
                date=parse_date(date_str, statement_year=self.context.statement_year),
                description=f"Check #{check_num}",
                debit=abs(amount),
                credit=None,
                balance=None
            ))

        # 2. Parse regular transactions
        lines = text.split('\\n')
        current_section = None
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Detect sections
            if _DEPOSITS_SECTION_RE.search(line):
                current_section = "credit"
                i += 1
                continue
            elif _WITHDRAWALS_SECTION_RE.search(line):
                current_section = "debit"
                i += 1
                continue
            elif _CHECK_SUMMARY_SECTION_RE.search(line) or _DAILY_BAL_SECTION_RE.search(line):
                current_section = "ignore"
                i += 1
                continue
                
            # Skip noise
            if not line or current_section == "ignore" or current_section is None:
                i += 1
                continue
            if any(p.search(line) for p in _SKIP_PATTERNS):
                i += 1
                continue
                
            is_debit = (current_section == "debit")
            
            # Type C - POS
            m_pos = _POS_LINE1_RE.search(line)
            if m_pos:
                date_str = m_pos.group(1)
                amount = parse_amount(m_pos.group(4), is_debit)
                desc_parts = [f"POS DEB {m_pos.group(2)} {m_pos.group(3)}"]
                
                # Consume continuation lines
                j = i + 1
                while j < len(lines) and _POS_MERCHANT_RE.match(lines[j]):
                    desc_parts.append(lines[j].strip())
                    j += 1
                    
                transactions.append(Transaction(
                    date=parse_date(date_str, statement_year=self.context.statement_year),
                    description=" ".join(desc_parts),
                    debit=abs(amount) if amount < 0 else None,
                    credit=amount if amount > 0 else None,
                    balance=None
                ))
                i = j
                continue
                
            # Type B - ACH Multi-line
            m_ach = _ACH_LINE1_RE.search(line)
            if m_ach and i+1 < len(lines):
                # Ensure it's not actually a simple line by checking if the next line is an ACH line 2
                m_ach2 = _ACH_LINE2_RE.match(lines[i+1])
                if m_ach2:
                    date_str = m_ach.group(1)
                    desc_parts = [m_ach.group(2).strip()]
                    amount = parse_amount(m_ach.group(3), is_debit)
                    
                    j = i + 1
                    while j < len(lines):
                        if _ACH_LINE2_RE.match(lines[j]) or _ACH_ID_RE.match(lines[j]) or _ACH_TRACE_RE.match(lines[j]) or _ACH_NAME_LINE_RE.match(lines[j]):
                            if not any(p.match(lines[j]) for p in [_ACH_ID_RE, _ACH_TRACE_RE, _ACH_LINE2_RE]):
                                # Only append name lines to description to keep it clean
                                desc_parts.append(lines[j].strip())
                            j += 1
                        else:
                            break
                            
                    transactions.append(Transaction(
                        date=parse_date(date_str, statement_year=self.context.statement_year),
                        description=" ".join(desc_parts),
                        debit=abs(amount) if amount < 0 else None,
                        credit=amount if amount > 0 else None,
                        balance=None
                    ))
                    i = j
                    continue

            # Type A - Simple Line
            m_simple = _SIMPLE_TXN_RE.search(line)
            if m_simple:
                date_str = m_simple.group(1)
                desc = m_simple.group(2).strip()
                amount = parse_amount(m_simple.group(3), is_debit)
                transactions.append(Transaction(
                    date=parse_date(date_str, statement_year=self.context.statement_year),
                    description=desc,
                    debit=abs(amount) if amount < 0 else None,
                    credit=amount if amount > 0 else None,
                    balance=None
                ))
                i += 1
                continue
                
            # Service charge block handling
            if "SERVICE CHARGE" in line.upper() and is_debit:
                # We can just extract it as a simple line, but avoid consuming its sub-components as separate charges
                # Sub-components have no leading date
                m_sc = re.search(r'^(\d{1,2}/\d{2})\s+SERVICE\s+CHARGE\s+([\d,]+\.\d{2})', line, re.IGNORECASE)
                if m_sc:
                    date_str = m_sc.group(1)
                    amount = parse_amount(m_sc.group(2), is_debit)
                    transactions.append(Transaction(
                        date=parse_date(date_str, statement_year=self.context.statement_year),
                        description="SERVICE CHARGE",
                        debit=abs(amount),
                        credit=None,
                        balance=None
                    ))
                    i += 1
                    # Skip continuation lines for SC
                    while i < len(lines):
                        next_upper = lines[i].upper().strip()
                        if "SERVICE CHARGE" in next_upper or "DEBIT ITEM FEE" in next_upper or "CR ITEM FEES IN S/C" in next_upper or "TRANSIT FEE IN S/C" in next_upper:
                            if not re.match(r'^\d{1,2}/\d{2}', next_upper):
                                i += 1
                            else:
                                break
                        else:
                            break
                    continue
            
            i += 1
            
        return transactions

    def parse(self) -> ParseResult:
        metadata = self.extract_metadata()
        transactions = self.extract_transactions()
        
        # Sort transactions by date since we extracted checks from a different section
        # But wait, date formats only have MM/DD, so sorting across year boundaries (Dec/Jan) might break.
        # But they are inside one month usually.
        # Better just rely on original extraction order and append checks at the end? Or sort properly.
        # In Python, string dates "YYYY-MM-DD" sort perfectly.
        transactions.sort(key=lambda x: x.date if x.date else "")

        # Daily balance reconciliation
        text = self._text()
        daily_balances = {}
        for m in _DAILY_BAL_ROW_RE.finditer(text):
            d_str = parse_date(m.group(1), statement_year=self.context.statement_year)
            bal = parse_amount(m.group(2))
            if d_str:
                daily_balances[d_str] = bal

        validation_errors = []
        running_balance = metadata.opening_balance

        if running_balance is not None:
            by_date = {}
            for t in transactions:
                by_date.setdefault(t.date, []).append(t)
                
            for d in sorted(by_date.keys()):
                day_txns = by_date[d]
                for t in day_txns:
                    if t.credit is not None:
                        running_balance += t.credit
                    elif t.debit is not None:
                        running_balance -= t.debit
                    running_balance = round(running_balance, 2)
                    t.balance = running_balance
                    
                # Check against stated daily balance
                if d in daily_balances:
                    stated_bal = daily_balances[d]
                    if abs(stated_bal - running_balance) > 0.05:
                        validation_errors.append(
                            f"Daily balance mismatch on {d}: computed {running_balance}, stated {stated_bal}"
                        )
                        # Sync to prevent cascade
                        running_balance = stated_bal
                        
        return ParseResult(
            metadata=metadata,
            transactions=transactions,
            confidence=calculate_confidence([txn.dict() for txn in transactions]),
            parser_id=self.parser_id,
            bank_id=metadata.bank_id,
            template_id="exchange_bank_comm_ckg",
            validation_errors=validation_errors,
            extra={},
        )

register_parser("EXCHANGE_BANK", ExchangeBankParser)
register_template_parser("exchange_bank_comm_ckg", ExchangeBankParser)
