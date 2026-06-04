# 🔧 Backend-Python Function Reference Guide

**Complete mapping of functions to their tasks**

---

## 📁 File Structure Overview

```
backend-python/app/
├── main.py                        # FastAPI application entry
├── core/
│   └── config.py                  # Configuration settings
├── models/
│   └── schemas.py                 # Data models (Pydantic)
├── routers/
│   └── ocr.py                     # API endpoints
└── services/                      # Business logic
    ├── pdf_type_detector.py       # PDF classification
    ├── digital_extractor.py       # Digital PDF extraction
    ├── image_preprocessor.py      # Image enhancement
    ├── ocr_extractor.py           # PaddleOCR wrapper
    ├── ocr_engine.py              # OCR operations
    ├── table_parser.py            # Table structure analysis
    ├── amount_utils.py            # Amount parsing
    ├── date_utils.py              # Date parsing
    ├── postprocessor.py           # Data cleaning
    ├── revenue_filter.py          # Revenue classification
    ├── metadata_extractor.py      # Extract bank info
    ├── hash_service.py            # Duplicate detection
    ├── file_service.py            # File operations
    └── ocr_pipeline.py            # Main orchestrator
```

---

## 📋 Complete Function List by Category

### 🚀 **1. API ENDPOINTS** (`routers/ocr.py`)

#### Main Processing Endpoints

```python
# API Routes
POST /api/ocr/process
POST /api/ocr/process-with-duplicate-check
GET  /

# Internal Helper Functions
async def write_file(upload_file, destination)
    → Save uploaded file to disk

def extract_with_pdfplumber(file_path)
    → Extract rows from digital PDF using pdfplumber

def _split_date_from_cell(cell, statement_year)
    → Extract date from start of cell (e.g., "1/02 MERCHANT")

def _parse_signed_amount_rows(rows, col_map, header_idx, statement_year)
    → Parse Date|Description|Amount format (PeoplesSouth style)

def _parse_multicolumn_rows(rows, col_map, header_idx, statement_year)
    → Parse Date|Check#|TranCode|Description|Amount|Balance format

def _detect_format(col_map, rows, header_idx)
    → Determine which parsing strategy to use

def process_single_statement(file_path)
    → Main processing orchestrator for a single statement

def _parse_lines_heuristic(rows, filename, statement_year)
    → Last-resort parser when no header found

def _parse_additions_subtractions_rows(rows, statement_year)
    → Parse US Bank "Additions/Subtractions" table format

def _parse_check_detail_rows(rows, statement_year)
    → Extract check details from "Number: XX Date: XX Amount: XX" format

def _statement_result(...)
    → Build final StatementResult object with all data
```

**Usage**: Main API for uploading and processing statements

---

### 📄 **2. PDF TYPE DETECTION** (`pdf_type_detector.py`)

```python
def detect_pdf_type(file_path, min_text_threshold=120, 
                    min_pages_with_text=2, total_chars_threshold=700,
                    image_heavy_threshold=0.6) -> "digital" | "scanned" | "hybrid"
    → Analyzes PDF to determine if it's digital (text-selectable) or scanned
    
    Process:
    - Opens PDF with PyMuPDF
    - Extracts text from first 8 pages
    - Counts characters per page
    - Counts embedded images
    - Returns classification based on text/image ratio
    
    Returns: "digital", "scanned", or "hybrid"
```

**Usage**: First step to decide extraction strategy

---

### 📝 **3. DIGITAL PDF EXTRACTION** (`digital_extractor.py`)

```python
def extract_digital_pdf(file_path) -> List[List[str]]
    → Extract rows from digital PDFs (text-selectable)
    
    Strategy (hierarchical):
    1. Try structured table extraction (pdfplumber tables)
    2. Fall back to word-level reconstruction
    3. Last resort: plain text split by newline
    
    Features:
    - Dynamic column gap detection
    - Y-axis tolerance based on median word height
    - Handles BMO-style layouts (no visible gridlines)
    
    Returns: List of rows, each row is a list of column values

# Alias for backward compatibility
extract_with_pdfplumber = extract_digital_pdf
```

**Usage**: Fast extraction for digital PDFs (5-15 seconds)

---

### 🖼️ **4. IMAGE PREPROCESSING** (`image_preprocessor.py`)

```python
def deskew_image(image) -> np.ndarray
    → Correct rotation/skew using minAreaRect angle detection
    
def remove_borders(image, border_pct=0.01) -> np.ndarray
    → Remove black borders from scanned pages (1% from each edge)
    
def assess_image_quality(image) -> dict
    → Assess image quality metrics
    Returns: {
        "contrast_ratio": 0-1,
        "noise_level": 0-1,
        "brightness": 0-255
    }
    
def denoise_image(image) -> np.ndarray
    → Apply bilateral filter for noise reduction
    
def apply_clahe(image) -> np.ndarray
    → Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
    → Enhances contrast for poor quality scans
    
def apply_sauvola_threshold(image, window_size=25) -> np.ndarray
    → Apply Sauvola binarization (better for uneven lighting)
    
def remove_scan_artifacts(image) -> np.ndarray
    → Remove small noise dots and thin lines
    
def preprocess_scanned_pdf(file_path, dpi=200) -> List[np.ndarray]
    → Complete preprocessing pipeline
    
    Process (conditional based on quality):
    1. Convert PDF to images at specified DPI
    2. Remove borders
    3. Assess quality
    4. Apply deskew if needed (low contrast/high noise)
    5. Apply CLAHE if needed (low contrast/brightness)
    6. Apply denoise if needed (high noise)
    7. Remove artifacts if needed (very high noise)
    
    Returns: List of preprocessed images (numpy arrays)
```

**Usage**: Prepares scanned images for OCR

---

### 🔍 **5. OCR EXTRACTION** (`ocr_extractor.py`)

```python
def _get_paddle_ocr()
    → Lazy initialization of PaddleOCR
    Configuration: lang="en", use_gpu=False, show_log=False
    
def _extract_text_from_v2_line(line) -> (text, box, score)
    → Extract text, bounding box, and confidence from OCR line
    
def _result_to_dict(result) -> dict
    → Convert OCR result to dictionary format
    
def _box_center(box) -> (x, y, height)
    → Calculate center coordinates and height from bounding box
    
def _normalize_ocr_lines(result) -> List[dict]
    → Normalize OCR output to standardized format
    Returns: List of {"text": str, "x": float, "y": float, "h": float, "score": float}
    
def ocr_lines_to_rows(lines) -> List[List[str]]
    → Convert OCR lines to table rows
    
    Process:
    1. Sort lines by Y-coordinate (top to bottom)
    2. Group lines by Y-position (same row)
    3. Detect header row with "additions/subtractions" pattern
    4. Align subsequent rows to header column positions
    
    Returns: List of rows (each row is list of cell values)
    
def _align_group_to_header(group, header_anchors) -> List[str]
    → Align OCR text to detected header column positions
    
def extract_ocr_rows(image) -> List[List[str]]
    → Main OCR extraction function
    
    Process:
    1. Run PaddleOCR on image
    2. Normalize results
    3. Convert to rows
    
    Returns: List of rows
```

**Usage**: Extracts text from preprocessed scanned images

---

### 📊 **6. TABLE STRUCTURE ANALYSIS** (`table_parser.py`)

```python
def map_columns(header_row) -> dict
    → Map column headers to their indices
    
    Supports 9 column types:
    - date: "Post Date", "Posted", "Date", "Txn Date"
    - description: "Transaction Description", "Particulars", "Narration"
    - debit: "Withdrawal", "Subtractions", "Debit", "DR"
    - credit: "Deposit", "Additions", "Credit", "CR"
    - balance: "Running Balance", "Closing Balance"
    - reference: "Ref No", "Cheque No", "Transaction ID"
    - check_number: "Check #", "Check No"
    - tran_code: "Tran Code", "Transaction Type"
    - amount: "Amount" (single signed column)
    
    Uses 90+ regex patterns for matching
    Prevents double-mapping (same index can't be two types)
    
    Returns: {"date": 0, "description": 1, "debit": 2, ...}
    
def detect_balance_column_from_data(data_rows, col_map) -> Optional[int]
    → Auto-detect balance column if not in header
    
    Logic: If 50%+ of rows have extra trailing column → it's balance
    
    Returns: Balance column index or None
    
def merge_wrapped_rows(rows, date_col_idx) -> List[List[str]]
    → Merge continuation rows (no date) into previous transaction
    
    Example:
    Input:  ["04/01", "Amazon", "123.45"]
            ["", "Order #12345", ""]
    Output: ["04/01", "Amazon Order #12345", "123.45"]
    
    Returns: List of merged rows
    
def detect_header_row(rows) -> Optional[int]
    → Find header row by keyword scoring
    
    Scoring:
    +1 for each keyword match (date, description, debit, etc.)
    +3 bonus if "date" AND "description" appear together
    -2 penalty if row contains actual date values
    -1 penalty if row contains dollar amounts
    
    Searches first 80 rows
    Requires minimum score of 2
    
    Returns: Index of header row or None
```

**Usage**: Identifies table structure and columns

---

### 💰 **7. AMOUNT PARSING** (`amount_utils.py`)

```python
def clean_amount(raw_value) -> Optional[float]
    → Parse amount string to float
    
    Handles:
    - Parentheses: (123.45) → -123.45
    - Currency symbols: $, ₹, Rs., INR, €, £, ¥
    - Dr/Cr suffixes: 1234.56 Dr, 1234.56 Cr
    - Trailing minus: 123.45- → -123.45
    - Thousand separators: 1,234.56 → 1234.56
    - European format: 1.234,56 → 1234.56
    - OCR corrections: O→0, l→1, S→5, B→8, G→6
    
    Rejects:
    - Masked accounts: XXXX1234
    - Long numbers: >12 digits
    - Text containing letters/slashes
    
    Returns: Float value (signed) or None
```

**Usage**: Cleans and parses transaction amounts

---

### 📅 **8. DATE PARSING & DATA CLEANING** (`postprocessor.py`)

```python
def parse_date(raw_text, statement_year=None, statement_month=None) -> Optional[str]
    → Parse date string to ISO format (YYYY-MM-DD)
    
    Supports 9 formats:
    1. YYYY-MM-DD (2003-10-08)
    2. DD/MM/YYYY (24/04/2023)
    3. MM/DD/YYYY (04/01/2025)
    4. DD/MM/YY (24/04/23)
    5. MM/DD/YY (04/01/25)
    6. Mon DD, YYYY (Jul 01, 2025)
    7. Mon DD (Jul 01)
    8. DD-Mon-YY (15-Jan-24)
    9. MM/DD (04/01)
    
    Features:
    - OCR correction before parsing (O→0, l→1)
    - Year inference from statement_year or current year
    - Ambiguous date resolution (tries MM/DD first, then DD/MM)
    
    Returns: ISO date string or None

def clean_amount(raw_value) -> Optional[float]
    → See amount_utils.py (same function)

def classify_debit_credit(row, col_map, balance_col) -> (debit, credit)
    → Classify transaction as debit or credit
    
    Three strategies:
    1. Separate columns: Use mapped debit/credit columns
    2. Single signed amount: Negative=debit, positive=credit
    3. Heuristic scan: Find amounts, use keywords to classify
    
    Keywords:
    - Debit: WITHDRAWAL, DEBIT, PURCHASE, CHARGE, FEE, PAYMENT
    - Credit: DEPOSIT, CREDIT, TRANSFER FROM, PAID IN, BANKCARD
    
    Returns: (debit_amount, credit_amount) tuple

def classify_signed_amount(raw_amount, row_text) -> (debit, credit)
    → Classify single signed amount value
    
    Rules:
    - Negative → debit
    - Positive + debit keywords → debit
    - Positive (default) → credit
    
    Returns: (debit_amount, credit_amount) tuple

def detect_statement_period(rows) -> (year, month)
    → Extract statement year/month from preamble
    
    Scans first 40 rows for:
    - Date patterns in cells
    - "04-2026" or "2026-04" formats
    - "Beginning Balance 12/01/25"
    
    Returns: (year, month) or (None, None)

def calculate_confidence(transactions) -> float
    → Calculate confidence score (0.0 - 1.0)
    
    Score per transaction:
    +0.3 if date present
    +0.2 if description >3 chars
    +0.4 if debit or credit present
    +0.1 if reference present
    
    Returns: Average score across all transactions

def deduplicate_transactions(transactions) -> List
    → Remove duplicate rows
    
    Key: (date, debit, credit, description[:100], reference)
    
    Returns: List of unique transactions
```

**Usage**: Parse dates, amounts, classify transactions

---

### 💵 **9. REVENUE CLASSIFICATION** (`revenue_filter.py`)

```python
def _normalise(text) -> str
    → Normalize text (lowercase, collapse whitespace)

def _first_rule_match(text, rules) -> (category, pattern) or None
    → Find first matching deduction rule

def classify_credit_revenue(description, account_holder, business_name) -> dict
    → Classify credit transaction as revenue or deduction
    
    Rule Priority:
    1. Owner Transfer Check
       - "sneads" + "money transfer" → Deduction
    
    2. Wire Special Logic
       - "wire" + "merchant/LOC" → Deduction
       - "wire" alone → Revenue
    
    3. Pattern Matching (90+ patterns)
       - Financing & Loans (30 patterns)
       - Internal Transfers (40 patterns)
       - Corrections & Perks (20 patterns)
    
    Returns: {
        "status": "revenue" or "deduction",
        "reason": category name or None,
        "rule": matched pattern or None
    }

def apply_revenue_filter(transactions, account_holder, business_name) -> dict
    → Apply revenue classification to all transactions
    
    Process:
    - Classify each credit transaction
    - Track deductions by category
    - Calculate adjusted revenue
    
    Returns: {
        "raw_credits": total credits,
        "adjusted_revenue": credits - deductions,
        "revenue_deductions": total deducted,
        "total_debits": total debits,
        "deduction_breakdown": {category: amount},
        "revenue_transactions": count,
        "deduction_transactions": count
    }

def generate_revenue_breakdown_report(transactions, revenue_snapshot) -> str
    → Generate detailed markdown report
    
    Returns: Formatted revenue breakdown string
```

**Usage**: Classify credits as revenue vs non-revenue

---

### 🔐 **10. DUPLICATE DETECTION** (`hash_service.py`)

```python
def generate_file_hash(file_path) -> str
    → Generate SHA-256 hash of file binary
    
    Returns: Hex digest string (e.g., "a1b2c3d4...")

def generate_content_hash(transactions, metadata) -> str
    → Generate SHA-256 hash of extracted content
    
    Process:
    1. Normalize account number, amounts, dates
    2. Sort transactions by date
    3. Create JSON string
    4. Generate SHA-256 hash
    
    Returns: Hex digest string
```

**Usage**: Prevent duplicate uploads

---

### 🔧 **11. MAIN ORCHESTRATOR** (`ocr_pipeline.py`)

```python
def _statement_result(...) -> StatementResult
    → Build final result object
    
    Combines:
    - Transactions
    - Metadata
    - Revenue snapshot
    - Hashes
    - Warnings
    
    Returns: StatementResult model

def _split_date_from_cell(cell, statement_year) -> (date, remainder)
    → Extract date from cell start (e.g., "1/02 MERCHANT")

def _parse_signed_amount_rows(rows, col_map, header_idx, statement_year) -> List[Transaction]
    → Parse signed amount format (PeoplesSouth style)

def _parse_multicolumn_rows(rows, col_map, header_idx, statement_year) -> List[Transaction]
    → Parse multicolumn format (MTD style)

def _detect_format(col_map, rows, header_idx) -> "signed_amount" | "multicolumn" | "standard"
    → Determine parsing strategy based on columns

def process_single_statement(file_path) -> StatementResult
    → Main processing function
    
    Process:
    1. Detect PDF type
    2. Extract rows (digital or OCR path)
    3. Detect statement period
    4. Try additions/subtractions parser
    5. Find header row
    6. Map columns
    7. Detect format
    8. Parse transactions
    9. Parse check details
    10. Deduplicate
    11. Classify revenue
    12. Extract metadata
    13. Calculate confidence
    14. Build result
    
    Returns: StatementResult

def _parse_lines_heuristic(rows, filename, statement_year) -> List[Transaction]
    → Last-resort parser (no clear structure)

def _parse_additions_subtractions_rows(rows, statement_year) -> List[Transaction]
    → Parse US Bank "Additions/Subtractions" format

def _parse_check_detail_rows(rows, statement_year) -> List[Transaction]
    → Extract check details from summary sections

async def process_uploaded_file(upload, with_duplicate_check) -> StatementResult
    → Async wrapper for file processing
    
    Process:
    1. Save uploaded file
    2. Generate file hash (if duplicate check enabled)
    3. Process statement
    4. Generate content hash (if duplicate check enabled)
    5. Clean up temporary file
    
    Returns: StatementResult
```

**Usage**: Main pipeline orchestrator

---

## 📦 Data Models (`models/schemas.py`)

```python
class Transaction(BaseModel):
    date: Optional[str]                    # ISO format YYYY-MM-DD
    description: str                       # Transaction description
    debit: Optional[float]                 # Withdrawal amount
    credit: Optional[float]                # Deposit amount
    balance: Optional[float]               # Running balance
    reference: Optional[str]               # Check #, Ref #, UTR
    source_line: str                       # Raw text
    transaction_type: Optional[str]        # "debit" | "credit"
    revenue_status: Optional[str]          # "revenue" | "deduction"
    revenue_deduction_reason: Optional[str] # Category
    revenue_rule: Optional[str]            # Matched pattern
    adjusted_revenue_amount: Optional[float] # Revenue amount

class StatementResult(BaseModel):
    filename: str
    transactions: List[Transaction]
    confidence: float
    pdf_type: str
    warnings: List[str]
    raw_text: Optional[str]
    bank_name: Optional[str]
    account_number: Optional[str]
    customer_number: Optional[str]
    current_balance: Optional[float]
    raw_credits: float
    adjusted_revenue: float
    revenue_deductions: float
    total_debits: float
    file_hash: Optional[str]
    content_hash: Optional[str]
    is_duplicate: bool
    duplicate_type: Optional[str]

class OCRResponse(BaseModel):
    status: str
    documents: List[StatementResult]
```

---

## 🎯 Quick Function Lookup Table

| Task | Function | File |
|------|----------|------|
| **Detect PDF type** | `detect_pdf_type()` | pdf_type_detector.py |
| **Extract digital PDF** | `extract_digital_pdf()` | digital_extractor.py |
| **Preprocess scanned image** | `preprocess_scanned_pdf()` | image_preprocessor.py |
| **Run OCR** | `extract_ocr_rows()` | ocr_extractor.py |
| **Find header row** | `detect_header_row()` | table_parser.py |
| **Map columns** | `map_columns()` | table_parser.py |
| **Merge wrapped rows** | `merge_wrapped_rows()` | table_parser.py |
| **Parse date** | `parse_date()` | postprocessor.py |
| **Clean amount** | `clean_amount()` | amount_utils.py |
| **Classify debit/credit** | `classify_debit_credit()` | postprocessor.py |
| **Classify revenue** | `classify_credit_revenue()` | revenue_filter.py |
| **Apply revenue filter** | `apply_revenue_filter()` | revenue_filter.py |
| **Generate file hash** | `generate_file_hash()` | hash_service.py |
| **Generate content hash** | `generate_content_hash()` | hash_service.py |
| **Process statement** | `process_single_statement()` | ocr_pipeline.py |
| **Calculate confidence** | `calculate_confidence()` | postprocessor.py |
| **Deduplicate transactions** | `deduplicate_transactions()` | postprocessor.py |

---

## 🔄 Processing Flow Diagram

```
1. API receives upload → write_file()
2. Detect PDF type → detect_pdf_type()
3a. Digital path → extract_digital_pdf()
3b. Scanned path → preprocess_scanned_pdf() → extract_ocr_rows()
4. Find header → detect_header_row()
5. Map columns → map_columns()
6. Detect format → _detect_format()
7. Parse rows → _parse_signed_amount_rows() | _parse_multicolumn_rows() | standard parser
8. Parse dates → parse_date()
9. Clean amounts → clean_amount()
10. Classify transactions → classify_debit_credit()
11. Classify revenue → classify_credit_revenue()
12. Apply filter → apply_revenue_filter()
13. Calculate confidence → calculate_confidence()
14. Build result → _statement_result()
15. Return JSON
```

---

## 📝 Usage Examples

### Example 1: Extract Digital PDF
```python
from pathlib import Path
from app.services.digital_extractor import extract_digital_pdf

rows = extract_digital_pdf(Path("statement.pdf"))
# Returns: [["Date", "Description", "Debit", "Credit"], ...]
```

### Example 2: Parse Date
```python
from app.services.postprocessor import parse_date

date = parse_date("04/01/2025", statement_year=2025)
# Returns: "2025-04-01"
```

### Example 3: Clean Amount
```python
from app.services.amount_utils import clean_amount

amount = clean_amount("($1,234.56)")
# Returns: -1234.56
```

### Example 4: Classify Revenue
```python
from app.services.revenue_filter import classify_credit_revenue

result = classify_credit_revenue("LINE OF CREDIT ADVANCE")
# Returns: {
#   "status": "deduction",
#   "reason": "Financing & Loans",
#   "rule": "\\bloc\\b"
# }
```

### Example 5: Process Statement
```python
from pathlib import Path
from app.services.ocr_pipeline import process_single_statement

result = process_single_statement(Path("statement.pdf"))
# Returns: StatementResult object
```

---

## 🎓 Key Concepts

### 1. Format Detection
The system detects 3 primary formats:
- **signed_amount**: Single amount column (negative=debit, positive=credit)
- **multicolumn**: Multiple columns including Check#, TranCode
- **standard**: Separate Debit and Credit columns

### 2. Revenue Classification
Uses 90+ regex patterns across 3 categories:
- **Financing & Loans** (30 patterns)
- **Internal Transfers** (40 patterns)
- **Corrections & Perks** (20 patterns)

### 3. Duplicate Detection
Two-level hashing:
- **File hash**: SHA-256 of PDF binary (fast check)
- **Content hash**: SHA-256 of extracted data (semantic check)

### 4. Confidence Scoring
Weighted scoring:
- Date: +0.3
- Description: +0.2
- Amount: +0.4
- Reference: +0.1

---

## ⚡ Performance Tips

1. **Digital PDFs are 3x faster**: Check PDF type first
2. **DPI matters**: 200 DPI is optimal balance (speed vs accuracy)
3. **Preprocessing is conditional**: Only applied when quality is poor
4. **Duplicate check is cheap**: File hash takes 60ms
5. **Column mapping is cached**: Reuse col_map within statement

---

*End of Function Reference Guide*
