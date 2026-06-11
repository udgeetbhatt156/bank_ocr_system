"""Reusable signed-amount statement parser."""

import re
from typing import Dict, List, Optional, Tuple

from app.models.schemas import Transaction
from app.parsers.base import BaseParser
from app.parsers.result import ParseResult, StatementMetadata
from app.services.amount_utils import clean_amount
from app.services.date_utils import parse_date
from app.services.metadata_extractor import extract_statement_metadata
from app.services.postprocessor import calculate_confidence, classify_signed_amount
from app.services.table_parser import detect_header_row, map_columns


def split_date_from_cell(
    cell: str,
    *,
    statement_year: Optional[int] = None,
) -> Tuple[Optional[str], str]:
    """Split a leading date from a row cell, preserving leftover text."""
    cell = cell.strip()
    m = re.match(r"^(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b\s*(.*)", cell)
    if m:
        date_str = parse_date(m.group(1), statement_year=statement_year)
        if date_str:
            return date_str, m.group(2).strip()
    m = re.match(r"^(\d{4}-\d{1,2}-\d{1,2})\b\s*(.*)", cell)
    if m:
        date_str = parse_date(m.group(1), statement_year=statement_year)
        if date_str:
            return date_str, m.group(2).strip()
    return None, cell


class SignedAmountParser(BaseParser):
    """Parser for Date/Description/Amount/Balance signed-amount layouts."""

    parser_id = "signed_amount"

    def extract_metadata(self) -> StatementMetadata:
        metadata = extract_statement_metadata(self.context.rows, self.extract_transactions())
        return StatementMetadata(
            bank_id=self.context.bank_id,
            bank_name=metadata.get("bank_name"),
            account_number=metadata.get("account_number"),
            customer_name=metadata.get("customer_name"),
            current_balance=metadata.get("current_balance"),
        )

    def extract_transactions(self) -> List[Transaction]:
        header_idx = detect_header_row(self.context.rows)
        if header_idx is None:
            header_idx = 0
        header_row = self.context.rows[header_idx] if header_idx < len(self.context.rows) else []
        col_map = map_columns(header_row) if header_row else {}
        return self._parse_signed_amount_rows(
            self.context.rows,
            col_map,
            header_idx,
            statement_year=self.context.statement_year,
        )

    def parse(self) -> ParseResult:
        transactions = self.extract_transactions()
        metadata_dict = extract_statement_metadata(self.context.rows, transactions)
        metadata = StatementMetadata(
            bank_id=self.context.bank_id,
            bank_name=metadata_dict.get("bank_name"),
            account_number=metadata_dict.get("account_number"),
            customer_name=metadata_dict.get("customer_name"),
            current_balance=metadata_dict.get("current_balance"),
        )
        return ParseResult(
            metadata=metadata,
            transactions=transactions,
            confidence=calculate_confidence([txn.dict() for txn in transactions]),
            parser_id=self.parser_id,
            bank_id=self.context.bank_id,
            template_id=self.context.template_id,
        )

    def _parse_signed_amount_rows(
        self,
        rows: List[List[str]],
        col_map: Dict,
        header_idx: int,
        *,
        statement_year: Optional[int] = None,
    ) -> List[Transaction]:
        del col_map  # Reserved for parser variants that need explicit columns.
        transactions: List[Transaction] = []
        data_rows = rows[header_idx + 1:]

        for row in data_rows:
            if not row or not any(str(c).strip() for c in row):
                continue

            date_str, leftover_desc = split_date_from_cell(
                str(row[0]), statement_year=statement_year
            )
            if not date_str:
                row_text = " ".join(str(c) for c in row).strip()
                if transactions and row_text:
                    previous = transactions[-1]
                    previous.description = f"{previous.description} {row_text}".strip()
                continue

            numeric_cells: List[Tuple[int, float]] = []
            for idx in range(len(row) - 1, -1, -1):
                val = clean_amount(str(row[idx]))
                if val is not None:
                    numeric_cells.append((idx, val))
                if len(numeric_cells) >= 2:
                    break

            if not numeric_cells:
                continue

            balance: Optional[float] = None
            if len(numeric_cells) >= 2:
                balance = abs(numeric_cells[0][1])
                amount_val = numeric_cells[1][1]
                amount_idx = numeric_cells[1][0]
                balance_idx = numeric_cells[0][0]
            else:
                amount_val = numeric_cells[0][1]
                amount_idx = numeric_cells[0][0]
                balance_idx = -1

            desc_parts = []
            if leftover_desc:
                desc_parts.append(leftover_desc)
            for idx in range(1, len(row)):
                if idx == amount_idx or idx == balance_idx:
                    continue
                cell_text = str(row[idx]).strip()
                if cell_text and clean_amount(cell_text) is None:
                    desc_parts.append(cell_text)
            description = " ".join(desc_parts).strip()

            if not description:
                description = " ".join(str(c) for c in row).strip()

            row_text = " ".join(str(c) for c in row)
            debit, credit = classify_signed_amount(str(amount_val), row_text)

            if debit is None and credit is None:
                continue

            transactions.append(Transaction(
                date=date_str,
                description=description,
                debit=debit,
                credit=credit,
                balance=balance,
            ))

        return transactions
