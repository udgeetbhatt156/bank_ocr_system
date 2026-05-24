# Requirements Specification: Advanced OCR Extraction

## Functional Requirements

### FR-1: Enhanced Table Detection

**Priority**: Critical  
**Status**: Not Started

#### Description
The system must accurately detect and extract tabular transaction data from bank statements regardless of layout complexity.

#### Acceptance Criteria
- **FR-1.1**: Detect tables with 2-6 columns
- **FR-1.2**: Handle tables spanning multiple pages
- **FR-1.3**: Identify column headers (Date, Description, Amount, Balance, etc.)
- **FR-1.4**: Detect merged cells and wrapped text
- **FR-1.5**: Handle tables with varying column widths
- **FR-1.6**: Achieve 95%+ table boundary detection accuracy

#### Test Cases
```
TC-1.1: Single-page statement with 4-column table
  Input: First Kansas Bank statement (page 1)
  Expected: Detect 1 table with columns [Date, Description, Amount, Balance]
  
TC-1.2: Multi-page statement with continued table
  Input: Fulton Bank statement (pages 1-12)
  Expected: Detect table continuation across all pages
  
TC-1.3: Statement with multiple separate tables
  Input: First Kansas Bank (Deposits + Withdrawals sections)
  Expected: Detect 2 distinct tables
```

---

### FR-2: Advanced Date Parsing

**Priority**: Critical  
**Status**: Not Started

#### Description
The system must parse dates in multiple formats commonly found in bank statements.

#### Acceptance Criteria
- **FR-2.1**: Parse dates in formats: MM/DD/YY, M/D/YY, MM/DD/YYYY, M/D/YYYY
- **FR-2.2**: Parse dates in formats: DD-MM-YY, DD/MM/YYYY, YYYY-MM-DD
- **FR-2.3**: Parse dates with month names: "Aug 15, 2025", "15 August 2025"
- **FR-2.4**: Handle date ranges: "08/01/25 through 08/31/25"
- **FR-2.5**: Infer year from statement period when year is omitted
- **FR-2.6**: Achieve 98%+ date parsing accuracy

#### Supported Formats
```python
SUPPORTED_DATE_FORMATS = [
    "%m/%d/%y",      # 8/01/25
    "%m/%d/%Y",      # 08/01/2025
    "%-m/%-d/%y",    # 8/1/25 (no leading zeros)
    "%m-%d-%y",      # 08-01-25
    "%d/%m/%Y",      # 01/08/2025 (European)
    "%Y-%m-%d",      # 2025-08-01 (ISO)
    "%b %d, %Y",     # Aug 01, 2025
    "%B %d, %Y",     # August 01, 2025
    "%d %b %Y",      # 01 Aug 2025
]
```

#### Test Cases
```
TC-2.1: Parse simple date format
  Input: "8/01/25"
  Expected: datetime(2025, 8, 1)
  
TC-2.2: Parse date with month name
  Input: "August 01, 2025"
  Expected: datetime(2025, 8, 1)
  
TC-2.3: Parse date range
  Input: "08/01/25 through 08/31/25"
  Expected: (datetime(2025, 8, 1), datetime(2025, 8, 31))
```

---

### FR-3: Intelligent Column Mapping

**Priority**: Critical  
**Status**: Not Started

#### Description
The system must automatically identify and map table columns to transaction fields.

#### Acceptance Criteria
- **FR-3.1**: Detect column types: Date, Description, Debit, Credit, Balance
- **FR-3.2**: Handle combined Amount columns (positive/negative values)
- **FR-3.3**: Handle separate Debit/Credit columns
- **FR-3.4**: Detect multi-line descriptions spanning multiple rows
- **FR-3.5**: Handle columns with varying alignment (left, right, center)
- **FR-3.6**: Achieve 90%+ column mapping accuracy

#### Column Detection Rules
```python
COLUMN_PATTERNS = {
    "date": r"(?i)(date|dt|trans\.?\s*date|eff\.?\s*date)",
    "description": r"(?i)(description|desc|transaction|memo|details)",
    "debit": r"(?i)(debit|withdrawal|payment|checks?|subtractions?)",
    "credit": r"(?i)(credit|deposit|addition|receipts?)",
    "amount": r"(?i)(amount|amt)",
    "balance": r"(?i)(balance|bal|running\s*balance)",
}
```

#### Test Cases
```
TC-3.1: Map standard 4-column layout
  Input: [Date, Description, Amount, Balance]
  Expected: {date: 0, description: 1, amount: 2, balance: 3}
  
TC-3.2: Map separate debit/credit columns
  Input: [Date, Description, Debit, Credit, Balance]
  Expected: {date: 0, description: 1, debit: 2, credit: 3, balance: 4}
  
TC-3.3: Handle multi-line descriptions
  Input: Row 1: "08/01  ACH Withdrawal Nav Technologies"
         Row 2: "       NAVPC PYMT, Todrick Walker"
  Expected: Merge into single transaction
```

---

### FR-4: Section-Aware Extraction

**Priority**: High  
**Status**: Not Started

#### Description
The system must understand document structure and extract transactions from different sections appropriately.

#### Acceptance Criteria
- **FR-4.1**: Detect section headers (DEPOSITS, WITHDRAWALS, CREDITS, DEBITS)
- **FR-4.2**: Associate transactions with correct section type
- **FR-4.3**: Handle statements with combined transaction lists
- **FR-4.4**: Detect section boundaries (horizontal lines, spacing, headers)
- **FR-4.5**: Achieve 95%+ section classification accuracy

#### Section Detection Patterns
```python
SECTION_HEADERS = {
    "deposits": r"(?i)(deposits?|credits?|additions?|receipts?)",
    "withdrawals": r"(?i)(withdrawals?|debits?|checks?|payments?|subtractions?)",
    "summary": r"(?i)(summary|account\s*activity|transactions?)",
    "balance": r"(?i)(balance|daily\s*balance)",
}
```

#### Test Cases
```
TC-4.1: Extract from separate sections
  Input: First Kansas Bank (DEPOSITS section + WITHDRAWALS section)
  Expected: All deposits marked as type="credit", all withdrawals as type="debit"
  
TC-4.2: Extract from combined transaction list
  Input: Fulton Bank (single Account Activity section)
  Expected: Classify each transaction based on amount sign
```

---

### FR-5: Transaction Type Classification

**Priority**: High  
**Status**: Not Started

#### Description
The system must automatically classify transactions as debits or credits.

#### Acceptance Criteria
- **FR-5.1**: Classify based on section (deposits = credit, withdrawals = debit)
- **FR-5.2**: Classify based on amount sign (positive = credit, negative = debit)
- **FR-5.3**: Classify based on keywords in description
- **FR-5.4**: Handle edge cases (refunds, reversals, fees)
- **FR-5.5**: Achieve 95%+ classification accuracy

#### Classification Rules
```python
DEBIT_KEYWORDS = [
    "withdrawal", "payment", "debit", "check", "draft", "fee",
    "charge", "purchase", "transfer out", "ach withdrawal"
]

CREDIT_KEYWORDS = [
    "deposit", "credit", "payment received", "refund", "interest",
    "transfer in", "ach deposit", "wire in"
]
```

#### Test Cases
```
TC-5.1: Classify based on section
  Input: Transaction in "DEPOSITS" section
  Expected: type="credit"
  
TC-5.2: Classify based on amount sign
  Input: Amount="-500.00"
  Expected: type="debit"
  
TC-5.3: Classify based on description
  Input: Description="ACH Withdrawal Nav Technologies"
  Expected: type="debit"
```

---

### FR-6: Amount Extraction & Validation

**Priority**: Critical  
**Status**: Not Started

#### Description
The system must accurately extract monetary amounts and validate their format.

#### Acceptance Criteria
- **FR-6.1**: Extract amounts with 2 decimal places
- **FR-6.2**: Handle amounts with thousand separators (1,234.56)
- **FR-6.3**: Handle amounts without decimal points (1234)
- **FR-6.4**: Detect negative amounts (parentheses or minus sign)
- **FR-6.5**: Validate amount format (reject invalid values)
- **FR-6.6**: Achieve 99%+ amount extraction accuracy

#### Amount Patterns
```python
AMOUNT_PATTERNS = [
    r"\$?\s*(\d{1,3}(?:,\d{3})*\.\d{2})",      # $1,234.56
    r"\$?\s*(\d+\.\d{2})",                      # $123.56
    r"\$?\s*(\d+)",                             # $123
    r"\(\$?\s*(\d{1,3}(?:,\d{3})*\.\d{2})\)",  # ($1,234.56) negative
    r"-\$?\s*(\d{1,3}(?:,\d{3})*\.\d{2})",     # -$1,234.56
]
```

#### Test Cases
```
TC-6.1: Extract standard amount
  Input: "$1,234.56"
  Expected: 1234.56
  
TC-6.2: Extract negative amount (parentheses)
  Input: "($500.00)"
  Expected: -500.00
  
TC-6.3: Extract amount without decimals
  Input: "$1234"
  Expected: 1234.00
```

---

### FR-7: Balance Reconciliation

**Priority**: High  
**Status**: Not Started

#### Description
The system must validate extracted transactions against statement balances.

#### Acceptance Criteria
- **FR-7.1**: Extract beginning and ending balances
- **FR-7.2**: Calculate expected ending balance from transactions
- **FR-7.3**: Compare calculated vs. stated ending balance
- **FR-7.4**: Flag discrepancies > $0.10
- **FR-7.5**: Provide reconciliation report
- **FR-7.6**: Achieve 95%+ reconciliation accuracy

#### Reconciliation Formula
```
Expected Ending Balance = Beginning Balance + Credits - Debits
Discrepancy = |Expected Ending Balance - Stated Ending Balance|
Status = "PASS" if Discrepancy <= $0.10 else "FAIL"
```

#### Test Cases
```
TC-7.1: Successful reconciliation
  Input: Beginning=$1,136.91, Credits=$219,125.37, Debits=$207,149.38
  Expected: Ending=$13,112.90, Status="PASS"
  
TC-7.2: Failed reconciliation
  Input: Beginning=$1,000, Credits=$500, Debits=$600, Stated Ending=$1,000
  Expected: Calculated=$900, Discrepancy=$100, Status="FAIL"
```

---

### FR-8: Confidence Scoring

**Priority**: Medium  
**Status**: Not Started

#### Description
The system must provide confidence scores for extracted data.

#### Acceptance Criteria
- **FR-8.1**: Score each transaction field (date, description, amount)
- **FR-8.2**: Score overall document extraction quality
- **FR-8.3**: Flag low-confidence transactions for review
- **FR-8.4**: Provide confidence breakdown by field type
- **FR-8.5**: Achieve correlation with actual accuracy

#### Confidence Factors
```python
CONFIDENCE_FACTORS = {
    "date_format_match": 0.3,      # Date matches expected format
    "amount_format_valid": 0.3,    # Amount has valid format
    "balance_reconciles": 0.2,     # Transaction fits balance flow
    "description_complete": 0.1,   # Description not truncated
    "column_alignment": 0.1,       # Data aligns with column boundaries
}
```

#### Confidence Levels
- **High (90-100%)**: Data extraction highly reliable
- **Medium (70-89%)**: Data likely correct, minor issues
- **Low (<70%)**: Data questionable, manual review recommended

#### Test Cases
```
TC-8.1: High confidence transaction
  Input: Well-formatted row with clear column boundaries
  Expected: confidence >= 0.90
  
TC-8.2: Low confidence transaction
  Input: Malformed row with unclear column boundaries
  Expected: confidence < 0.70, flagged for review
```

---

### FR-9: Multi-Page Processing

**Priority**: High  
**Status**: Not Started

#### Description
The system must handle bank statements spanning multiple pages.

#### Acceptance Criteria
- **FR-9.1**: Detect page breaks in transaction tables
- **FR-9.2**: Continue extraction across pages
- **FR-9.3**: Handle repeated headers on each page
- **FR-9.4**: Merge transactions from all pages
- **FR-9.5**: Maintain transaction order
- **FR-9.6**: Process 50+ page statements

#### Test Cases
```
TC-9.1: Multi-page statement
  Input: Fulton Bank (12 pages)
  Expected: Extract all transactions from all pages in order
  
TC-9.2: Statement with repeated headers
  Input: Statement with "Date | Description | Amount" on each page
  Expected: Skip repeated headers, extract only data rows
```

---

### FR-10: Error Handling & Recovery

**Priority**: High  
**Status**: Not Started

#### Description
The system must gracefully handle errors and provide meaningful feedback.

#### Acceptance Criteria
- **FR-10.1**: Detect corrupted or malformed PDFs
- **FR-10.2**: Handle PDFs with no extractable text
- **FR-10.3**: Provide specific error messages
- **FR-10.4**: Log errors for debugging
- **FR-10.5**: Continue processing other documents on error
- **FR-10.6**: Return partial results when possible

#### Error Types
```python
ERROR_TYPES = {
    "PDF_CORRUPTED": "PDF file is corrupted or unreadable",
    "NO_TEXT_FOUND": "No extractable text found in PDF",
    "NO_TABLES_DETECTED": "No transaction tables detected",
    "DATE_PARSING_FAILED": "Unable to parse dates in document",
    "BALANCE_MISMATCH": "Transactions do not reconcile with stated balance",
    "TIMEOUT": "Processing exceeded maximum time limit",
}
```

#### Test Cases
```
TC-10.1: Handle corrupted PDF
  Input: Corrupted PDF file
  Expected: Return error "PDF_CORRUPTED" with details
  
TC-10.2: Handle scanned PDF without OCR
  Input: Image-based PDF, OCR disabled
  Expected: Return error "NO_TEXT_FOUND" with suggestion to enable OCR
```

---

## Non-Functional Requirements

### NFR-1: Performance

**Priority**: High

- **NFR-1.1**: Process digital PDFs at < 10 seconds per page
- **NFR-1.2**: Process scanned PDFs at < 30 seconds per page
- **NFR-1.3**: Support concurrent processing of 5+ documents
- **NFR-1.4**: Memory usage < 500MB per document
- **NFR-1.5**: CPU usage < 80% during processing

---

### NFR-2: Scalability

**Priority**: Medium

- **NFR-2.1**: Handle PDFs up to 50 pages
- **NFR-2.2**: Handle PDFs up to 50MB file size
- **NFR-2.3**: Process 100+ documents per hour
- **NFR-2.4**: Support horizontal scaling (multiple workers)

---

### NFR-3: Reliability

**Priority**: High

- **NFR-3.1**: 99% uptime for OCR service
- **NFR-3.2**: Automatic retry on transient failures
- **NFR-3.3**: Graceful degradation on resource constraints
- **NFR-3.4**: Data integrity validation at each step

---

### NFR-4: Maintainability

**Priority**: Medium

- **NFR-4.1**: Modular architecture with clear separation of concerns
- **NFR-4.2**: Comprehensive logging for debugging
- **NFR-4.3**: Configuration-based parser rules (no hardcoding)
- **NFR-4.4**: Unit test coverage > 80%
- **NFR-4.5**: Integration test coverage for all bank formats

---

### NFR-5: Security

**Priority**: High

- **NFR-5.1**: No external API calls (data privacy)
- **NFR-5.2**: Secure file handling (no arbitrary code execution)
- **NFR-5.3**: Input validation to prevent injection attacks
- **NFR-5.4**: Audit logging for all processing activities

---

### NFR-6: Usability

**Priority**: Medium

- **NFR-6.1**: Clear error messages for end users
- **NFR-6.2**: Progress indicators for long-running operations
- **NFR-6.3**: Detailed extraction reports
- **NFR-6.4**: API documentation with examples

---

## Traceability Matrix

| Requirement | Test Cases | Design Components | Implementation Files |
|-------------|------------|-------------------|---------------------|
| FR-1 | TC-1.1, TC-1.2, TC-1.3 | TableDetector | table_detector.py |
| FR-2 | TC-2.1, TC-2.2, TC-2.3 | DateParser | date_parser.py |
| FR-3 | TC-3.1, TC-3.2, TC-3.3 | ColumnMapper | column_mapper.py |
| FR-4 | TC-4.1, TC-4.2 | SectionDetector | section_detector.py |
| FR-5 | TC-5.1, TC-5.2, TC-5.3 | TransactionClassifier | transaction_classifier.py |
| FR-6 | TC-6.1, TC-6.2, TC-6.3 | AmountExtractor | amount_extractor.py |
| FR-7 | TC-7.1, TC-7.2 | BalanceReconciler | balance_reconciler.py |
| FR-8 | TC-8.1, TC-8.2 | ConfidenceScorer | confidence_scorer.py |
| FR-9 | TC-9.1, TC-9.2 | MultiPageProcessor | multipage_processor.py |
| FR-10 | TC-10.1, TC-10.2 | ErrorHandler | error_handler.py |

---

**Status**: Draft - Ready for Review  
**Next Step**: Design Specification  
**Estimated Effort**: 2-3 weeks development + 1 week testing
