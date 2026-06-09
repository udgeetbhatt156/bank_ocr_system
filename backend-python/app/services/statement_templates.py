"""
Starter registry for bank statement layout templates.

Templates describe layout families. They are intentionally lightweight so new
banks can be added by extending data, not by growing parser conditionals.
"""
from dataclasses import dataclass, field
import re
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class StatementTemplate:
    template_id: str
    bank_name: str
    layout_family: str
    parser_format: str
    bank_patterns: List[str]
    header_keywords: List[str]
    amount_rules: Dict[str, bool] = field(default_factory=dict)
    stop_keywords: List[str] = field(default_factory=list)
    sample_files: List[str] = field(default_factory=list)


TEMPLATES: List[StatementTemplate] = [
    StatementTemplate(
        template_id="genreich_signed_amount_v1",
        bank_name="Navy Federal Credit Union",
        layout_family="single_signed_amount_with_running_balance",
        parser_format="signed_amount",
        bank_patterns=[
            "genreich",
            "statement of account",
            "navyfederal.org",
            "navy federal",
        ],
        header_keywords=["date", "transaction detail", "amount", "balance"],
        amount_rules={
            "trailing_minus_is_debit": True,
            "positive_is_credit": True,
        },
        stop_keywords=["items paid", "average daily balance"],
        sample_files=[
            "GENREICH_FEBUARY_1_.pdf",
            "GENREICH_APRIL_1_.pdf",
        ],
    ),
    StatementTemplate(
        template_id="chase_repeated_blocks_v1",
        bank_name="JPMorgan Chase",
        layout_family="repeated_horizontal_blocks",
        parser_format="repeated_blocks",
        bank_patterns=[
            "jpmorgan chase",
            "chase.com",
            "perry systems",
            "chase total checking",
        ],
        header_keywords=["date", "description", "amount","Account Number."],
        amount_rules={
            "section_context": True,
            "negative_is_debit": True,
        },
        stop_keywords=["service fee", "overdraft"],
        sample_files=[
            "20260326173751_PERRY_SYSTEMS_LLC_FEB_.pdf",
            "20260326173751_PERRY_SYSTEMS_LLC_jan.pdf",
        ],
    ),
    StatementTemplate(
        template_id="bank_of_america_sectioned_v1",
        bank_name="Bank of America",
        layout_family="sectioned_deposits_withdrawals",
        parser_format="sectioned",
        bank_patterns=[
            "bank of america",
            "bankofamerica.com",
            "business advantage",
            "zason latino",
            "bankcard 1250",
        ],
        header_keywords=[
            "deposits and other credits",
            "withdrawals and other debits",
            "checks",
            "date",
            "description",
            "amount",
        ],
        amount_rules={
            "section_deposits_are_credit": True,
            "section_withdrawals_are_debit": True,
        },
        stop_keywords=["daily balance", "service fees"],
        sample_files=["april.pdf", "Jan.pdf"],
    ),
    StatementTemplate(
        template_id="sofi_digital_activity_v1",
        bank_name="SoFi Bank",
        layout_family="signed_amount_with_type_column",
        parser_format="sofi_signed_type",
        bank_patterns=[
            "sofi",
            "sofi bank",
            "sofi.com",
            "integrative llc",
            "sofi checking",
            "sofi insured deposit",
        ],
        header_keywords=["date", "type", "description", "amount", "balance"],
        amount_rules={
            "plus_is_credit": True,
            "minus_is_debit": True,
            "single_signed_column": True,
        },
        stop_keywords=[
            "interest accrues daily",
            "sofi insured deposit program",
            "important information",
            "how to contact us",
            "deposit agreement",
            "opening balance",
        ],
        sample_files=[
            "SoFi_Apr_2026_Statement.pdf",
            "SoFi_January_2026.pdf",
            "SoFi_February_2026.pdf",
        ],
    ),
    StatementTemplate(
        template_id="navy_federal_scanned_v1",
        bank_name="Navy Federal Credit Union",
        layout_family="scanned_ocr_table",
        parser_format="standard",
        bank_patterns=["navy federal", "navy_federal"],
        header_keywords=["date", "description", "amount", "balance"],
        amount_rules={
            "negative_is_debit": True,
            "positive_is_credit": True,
        },
        sample_files=["Navy_Federal_December_Business_Statement_.pdf"],
    ),
    StatementTemplate(
        template_id="peoplessouth_signed_amount_v1",
        bank_name="PeopleSouth Bank",
        layout_family="single_signed_amount_with_running_balance",
        parser_format="signed_amount",
        bank_patterns=[
            "peoplessouth",
            "people south",
            "sneads tire and oil",
        ],
        header_keywords=["date", "description", "amount"],
        amount_rules={
            "negative_is_debit": True,
            "trailing_minus_is_debit": True,
            "parentheses_is_debit": True,
            "positive_is_credit": True,
        },
        sample_files=["01-2026 SNEADS TIRE AND OIL LLC.pdf"],
    ),
    StatementTemplate(
        template_id="peoplessouth_activity_statement_v1",
        bank_name="PeopleSouth Bank",
        layout_family="multicolumn_activity_statement",
        parser_format="multicolumn",
        bank_patterns=[
            "peoplessouth",
            "people south",
            "mtd sneads tire and oil",
        ],
        header_keywords=[
            "date",
            "check",
            "trancode",
            "description",
            "amount",
            "balance",
        ],
        amount_rules={
            "parentheses_is_debit": True,
            "positive_is_credit": True,
        },
        sample_files=["04-2026 MTD SNEADS TIRE AND OIL LLC.pdf"],
    ),
    StatementTemplate(
        template_id="bancfirst_sectioned_activity_v1",
        bank_name="BancFirst",
        layout_family="sectioned_deposits_withdrawals",
        parser_format="sectioned",
        bank_patterns=[
            "bancfirst",
            "4452334719",
            "business essentials",
            "church ave",
        ],
        header_keywords=[
            "beginning balance",
            "deposits",
            "withdrawals",
            "card activity",
            "other debits",
            "ending balance",
            "activity description",
        ],
        amount_rules={
            "section_withdrawals_are_debit": True,
            "section_deposits_are_credit": True,
            "balance_delta_validation": True,
        },
        stop_keywords=["daily balance", "ending balance", "checks in number"],
        sample_files=[
            "4719-December-BancFirst.pdf",
            "4719-January-BancFirst.pdf",
        ],
    ),

    # Citibank — split Debits / Credits columns with running balance
    StatementTemplate(
        template_id="citi_streamlined_checking_v1",
        bank_name="Citibank",
        layout_family="separate_debit_credit_with_balance",
        parser_format="standard",
        bank_patterns=[
            "citibank",
            "citibusiness",
            "cbo services",
            "streamlined checking",
            "citi.com",
        ],
        header_keywords=[
            "date",
            "description",
            "debits",
            "credits",
            "balance",
        ],
        amount_rules={
            "debit_column_is_debit": True,
            "credit_column_is_credit": True,
        },
        stop_keywords=[
            "service charge summary",
            "average daily collected balance",
        ],
        sample_files=[
            "Citi_XLRM_LLC_Feb_28_to_March_26_2026.pdf",
            "Citi_XLRM_LLC_Jan_27_to_Feb_27_2026.pdf",
        ],
    ),
    # Wells Fargo — Check# / Credits / Debits / Ending Daily Balance
    StatementTemplate(
        template_id="wells_fargo_business_checking_v1",
        bank_name="Wells Fargo",
        layout_family="separate_debit_credit_with_daily_balance",
        parser_format="standard",
        bank_patterns=[
            "wells fargo",
            "wellsfargo.com",
            "initiate business checking",
            "botachic designs",
        ],
        header_keywords=[
            "date",
            "check number",
            "description",
            "deposits/credits",
            "withdrawals/debits",
            "ending daily balance",
        ],
        amount_rules={
            "debit_column_is_debit": True,
            "credit_column_is_credit": True,
        },
        stop_keywords=[
            "totals",
            "monthly service fee summary",
            "account transaction fees",
        ],
        sample_files=["Feb_2026_Botachic_Designs_llc.pdf"],
    ),
    # Chase Total Checking — sectioned (Deposits / ATM & Debit /
    #   Electronic / Fees) with per-section Date | Description | Amount
    StatementTemplate(
        template_id="chase_total_checking_sectioned_v1",
        bank_name="JPMorgan Chase",
        layout_family="sectioned_deposits_withdrawals",
        parser_format="sectioned",
        bank_patterns=[
            "jpmorgan chase",
            "chase.com",
            "chase total checking",
        ],
        header_keywords=[
            "Account Number",
            "deposits and additions",
            "atm & debit card withdrawals",
            "electronic withdrawals",
            "fees and other withdrawals",
            "date",
            "description",
            "amount"
        ],
        amount_rules={
            "section_deposits_are_credit": True,
            "section_withdrawals_are_debit": True,
        },
        stop_keywords=[
            "service fee",
            "overdraft and returned item",
            "total deposits",
            "total atm",
            "total electronic",
            "total fees",
        ],
        sample_files=["20260326173751_PERRY_SYSTEMS_LLC_jan.pdf"],
    ),
    # Generic fallback templates
    StatementTemplate(
        template_id="generic_additions_subtractions_v1",
        bank_name="Unknown",
        layout_family="additions_subtractions",
        parser_format="additions_subtractions",
        bank_patterns=[],
        header_keywords=["date", "description", "additions", "subtractions"],
        amount_rules={
            "additions_are_credit": True,
            "subtractions_are_debit": True,
        },
    ),
    StatementTemplate(
        template_id="generic_debit_credit_v1",
        bank_name="Unknown",
        layout_family="separate_debit_credit",
        parser_format="standard",
        bank_patterns=[],
        header_keywords=["date", "description", "debit", "credit"],
        amount_rules={
            "debit_column_is_debit": True,
            "credit_column_is_credit": True,
        },
    ),
]


def _flatten(rows: List[List[str]], limit: int = 80) -> str:
    return "\n".join(" ".join(str(cell) for cell in row) for row in rows[:limit]).lower()


def _contains_all(text: str, terms: Iterable[str]) -> bool:
    return all(term.lower() in text for term in terms)


def select_statement_template(
    rows: List[List[str]],
    *,
    filename: str = "",
    bank_name: Optional[str] = None,
) -> Optional[StatementTemplate]:
    """Select the best starter template from extracted rows and filename."""
    text = f"{filename}\n{bank_name or ''}\n{_flatten(rows)}".lower()
    best: Optional[StatementTemplate] = None
    best_score = 0

    for template in TEMPLATES:
        score = 0
        for pattern in template.bank_patterns:
            if pattern and re.search(re.escape(pattern.lower()), text):
                score += 4
        for keyword in template.header_keywords:
            if keyword.lower() in text:
                score += 1
        for sample_file in template.sample_files:
            if sample_file.lower() in text:
                score += 6

        if score > best_score:
            best = template
            best_score = score

    if best and best_score >= 3:
        return best

    if _contains_all(text, ["date", "description", "additions"]):
        return next(t for t in TEMPLATES if t.template_id == "generic_additions_subtractions_v1")

    if _contains_all(text, ["date", "description", "debit", "credit"]):
        return next(t for t in TEMPLATES if t.template_id == "generic_debit_credit_v1")

    return None
