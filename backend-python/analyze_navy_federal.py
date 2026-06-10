"""
Navy Federal December Business Statement — OCR extraction & layout analysis.

This script:
1. Runs PaddleOCR on each page of the scanned PDF
2. Prints the raw OCR rows with spatial grouping
3. Identifies the table structure, header row, and column layout
4. Tests the current parser against the extracted data
"""
import logging
import json
from pathlib import Path
from app.services.image_preprocessor import preprocess_scanned_pdf
from app.services.ocr_extractor import extract_ocr_rows_with_debug
from app.services.table_parser import (
    detect_header_row,
    map_columns,
    normalize_header_row,
    merge_wrapped_rows,
    detect_balance_column_from_data,
)
from app.services.postprocessor import (
    detect_statement_period,
    parse_date,
    clean_amount,
    classify_debit_credit,
    classify_signed_amount,
)
from app.services.statement_templates import select_statement_template
from app.services.metadata_extractor import extract_statement_metadata

logging.basicConfig(level=logging.INFO, format='%(name)s - %(message)s')

pdf_path = Path('combined-all-pdf/Navy_Federal_December_Business_Statement_.pdf')
print(f'Analyzing: {pdf_path.name}')
print(f'File size: {pdf_path.stat().st_size:,} bytes')

# Step 1: Preprocess & OCR
print('\n' + '='*80)
print('STEP 1: IMAGE PREPROCESSING & OCR')
print('='*80)

images = preprocess_scanned_pdf(pdf_path, dpi=200)
print(f'Preprocessed {len(images)} page images')

all_rows = []
for page_num, img in enumerate(images, start=1):
    print(f'\n--- PAGE {page_num} ---')
    ocr_rows, debug_page = extract_ocr_rows_with_debug(img, page_number=page_num)
    print(f'  OCR rows: {len(ocr_rows)}')
    for i, row in enumerate(ocr_rows):
        row_text = ' | '.join(str(c) for c in row)
        print(f'  [{i:3d}] {row_text}')
    all_rows.extend(ocr_rows)

print(f'\nTotal rows extracted: {len(all_rows)}')

# Step 2: Statement period detection
print('\n' + '='*80)
print('STEP 2: STATEMENT PERIOD DETECTION')
print('='*80)
stmt_year, stmt_month = detect_statement_period(all_rows)
print(f'  Year: {stmt_year}, Month: {stmt_month}')

# Step 3: Metadata extraction
print('\n' + '='*80)
print('STEP 3: METADATA EXTRACTION')
print('='*80)
meta = extract_statement_metadata(all_rows, [], header_idx=None)
print(f'  Bank: {meta["bank_name"]}')
print(f'  Account: {meta["account_number"]}')
print(f'  Customer: {meta["customer_name"]}')
print(f'  Balance: {meta["current_balance"]}')

# Step 4: Template selection
print('\n' + '='*80)
print('STEP 4: TEMPLATE SELECTION')
print('='*80)
template = select_statement_template(
    all_rows,
    filename=pdf_path.name,
    bank_name=meta.get('bank_name'),
)
if template:
    print(f'  Template: {template.template_id}')
    print(f'  Layout: {template.layout_family}')
    print(f'  Parser: {template.parser_format}')
    print(f'  Bank: {template.bank_name}')
else:
    print('  No template matched!')

# Step 5: Header detection & column mapping
print('\n' + '='*80)
print('STEP 5: HEADER DETECTION & COLUMN MAPPING')
print('='*80)
header_idx = detect_header_row(all_rows)
print(f'  Header row index: {header_idx}')
if header_idx is not None and header_idx < len(all_rows):
    header_row = all_rows[header_idx]
    print(f'  Header: {header_row}')
    normalized = normalize_header_row(header_row)
    print(f'  Normalized: {normalized}')
    col_map = map_columns(header_row)
    print(f'  Column map: {col_map}')

# Step 6: Show data rows and parse attempts
print('\n' + '='*80)
print('STEP 6: DATA ROWS ANALYSIS')
print('='*80)
if header_idx is not None:
    data_rows = all_rows[header_idx + 1:]
    print(f'  Data rows: {len(data_rows)}')
    
    # Show first 20 data rows with parsing
    for i, row in enumerate(data_rows[:30]):
        row_text = ' | '.join(str(c) for c in row)
        
        # Try date parsing on first cell
        date = parse_date(str(row[0]), statement_year=stmt_year) if row else None
        
        # Try amount parsing on each cell
        amounts = []
        for j, cell in enumerate(row):
            amt = clean_amount(str(cell))
            if amt is not None:
                amounts.append((j, amt))
        
        date_marker = f'DATE={date}' if date else 'no-date'
        amt_marker = f'AMTs={amounts}' if amounts else 'no-amt'
        print(f'  [{i:3d}] {row_text}')
        print(f'        → {date_marker} | {amt_marker}')

# Step 7: Run full pipeline
print('\n' + '='*80)
print('STEP 7: FULL PIPELINE RESULT')
print('='*80)
from app.services.ocr_pipeline import process_single_statement
result = process_single_statement(pdf_path)
print(f'  Transactions: {len(result.transactions)}')
print(f'  Confidence: {result.confidence}')
print(f'  Bank: {result.bank_name}')
print(f'  Warnings: {result.warnings}')

if result.transactions:
    print(f'\n  All transactions:')
    for i, t in enumerate(result.transactions):
        desc = t.description[:60] if t.description else ''
        print(f'  [{i:3d}] {t.date} | {desc:<60} | D={t.debit} C={t.credit} B={t.balance}')
    
    total_d = sum(float(t.debit or 0) for t in result.transactions)
    total_c = sum(float(t.credit or 0) for t in result.transactions)
    print(f'\n  Total Debits: ${total_d:,.2f}')
    print(f'  Total Credits: ${total_c:,.2f}')
