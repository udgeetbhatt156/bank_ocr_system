# ⚡ Quick Function Map - Backend OCR System

**One-page reference: Function → Purpose**

---

## 🎯 Core Processing Functions

| Function | What It Does | Where |
|----------|-------------|-------|
| `process_single_statement()` | **MAIN ORCHESTRATOR** - Processes entire statement end-to-end | ocr_pipeline.py |
| `detect_pdf_type()` | Determines if PDF is digital or scanned | pdf_type_detector.py |
| `extract_digital_pdf()` | Fast text extraction from digital PDFs | digital_extractor.py |
| `preprocess_scanned_pdf()` | Enhances scanned images for OCR | image_preprocessor.py |
| `extract_ocr_rows()` | Runs PaddleOCR on images | ocr_extractor.py |

---

## 📊 Table Analysis Functions

| Function | What It Does | Where |
|----------|-------------|-------|
| `detect_header_row()` | Finds header row by keyword scoring | table_parser.py |
| `map_columns()` | Maps headers to column indices (date→0, desc→1) | table_parser.py |
| `merge_wrapped_rows()` | Merges continuation rows without dates | table_parser.py |
| `detect_balance_column_from_data()` | Auto-detects balance column | table_parser.py |

---

## 🧹 Data Cleaning Functions

| Function | What It Does | Where |
|----------|-------------|-------|
| `parse_date()` | Parses 9 date formats → ISO format | postprocessor.py |
| `clean_amount()` | Cleans amounts (currency, OCR errors) | amount_utils.py |
| `classify_debit_credit()` | Classifies as debit or credit | postprocessor.py |
| `classify_signed_amount()` | Handles signed amounts (neg=debit) | postprocessor.py |
| `deduplicate_transactions()` | Removes duplicate rows | postprocessor.py |

---

## 💰 Revenue Classification Functions

| Function | What It Does | Where |
|----------|-------------|-------|
| `classify_credit_revenue()` | Classifies credit as revenue or deduction | revenue_filter.py |
| `apply_revenue_filter()` | Applies classification to all transactions | revenue_filter.py |
| `generate_revenue_breakdown_report()` | Creates detailed revenue report | revenue_filter.py |

---

## 🔐 Security Functions

| Function | What It Does | Where |
|----------|-------------|-------|
| `generate_file_hash()` | SHA-256 hash of file binary | hash_service.py |
| `generate_content_hash()` | SHA-256 hash of extracted data | hash_service.py |

---

## 🎨 Format-Specific Parsers

| Function | What It Does | Where |
|----------|-------------|-------|
| `_parse_signed_amount_rows()` | Parses Date\|Desc\|Amount format | ocr_pipeline.py |
| `_parse_multicolumn_rows()` | Parses Date\|Check#\|TranCode\|Desc\|Amt | ocr_pipeline.py |
| `_parse_additions_subtractions_rows()` | Parses US Bank format | ocr_pipeline.py |
| `_parse_check_detail_rows()` | Extracts check summary sections | ocr_pipeline.py |
| `_parse_lines_heuristic()` | Last-resort parser (no structure) | ocr_pipeline.py |

---

## 🔧 Utility Functions

| Function | What It Does | Where |
|----------|-------------|-------|
| `calculate_confidence()` | Scores extraction quality (0.0-1.0) | postprocessor.py |
| `detect_statement_period()` | Extracts year/month from header | postprocessor.py |
| `_split_date_from_cell()` | Extracts date from cell start | ocr_pipeline.py |
| `_detect_format()` | Determines parsing strategy | ocr_pipeline.py |
| `_statement_result()` | Builds final result object | ocr_pipeline.py |

---

## 🖼️ Image Processing Functions

| Function | What It Does | Where |
|----------|-------------|-------|
| `assess_image_quality()` | Analyzes contrast, noise, brightness | image_preprocessor.py |
| `deskew_image()` | Corrects rotation/skew | image_preprocessor.py |
| `remove_borders()` | Removes scan borders | image_preprocessor.py |
| `denoise_image()` | Reduces noise | image_preprocessor.py |
| `apply_clahe()` | Enhances contrast | image_preprocessor.py |
| `remove_scan_artifacts()` | Removes dots/lines | image_preprocessor.py |

---

## 🔍 OCR Helper Functions

| Function | What It Does | Where |
|----------|-------------|-------|
| `_get_paddle_ocr()` | Initializes PaddleOCR | ocr_extractor.py |
| `_normalize_ocr_lines()` | Standardizes OCR output | ocr_extractor.py |
| `ocr_lines_to_rows()` | Converts OCR lines to table rows | ocr_extractor.py |
| `_align_group_to_header()` | Aligns text to header columns | ocr_extractor.py |

---

## 🚀 API Functions (routers/ocr.py)

| Function | What It Does |
|----------|-------------|
| `POST /api/ocr/process` | Upload & process statement |
| `POST /api/ocr/process-with-duplicate-check` | Process with duplicate prevention |
| `GET /` | Health check |
| `write_file()` | Save uploaded file |

---

## 📦 Processing Pipeline (Step-by-Step)

```
1. Upload                    → write_file()
2. Detect Type               → detect_pdf_type()
3a. Digital                  → extract_digital_pdf()
3b. Scanned                  → preprocess_scanned_pdf() → extract_ocr_rows()
4. Find Header               → detect_header_row()
5. Map Columns               → map_columns()
6. Detect Format             → _detect_format()
7. Parse Transactions        → _parse_signed_amount_rows() / _parse_multicolumn_rows() / standard
8. Parse Dates               → parse_date()
9. Clean Amounts             → clean_amount()
10. Classify Debit/Credit    → classify_debit_credit()
11. Classify Revenue         → classify_credit_revenue() → apply_revenue_filter()
12. Deduplicate              → deduplicate_transactions()
13. Calculate Confidence     → calculate_confidence()
14. Build Result             → _statement_result()
15. Return JSON
```

---

## 💡 Key Function Categories

### **Entry Points** (Start Here)
- `process_single_statement()` - Main processing
- `process_uploaded_file()` - Async wrapper

### **Path Splitters** (Decision Makers)
- `detect_pdf_type()` - Digital or scanned?
- `_detect_format()` - Which parser?

### **Extractors** (Get Raw Data)
- `extract_digital_pdf()` - From digital PDFs
- `extract_ocr_rows()` - From images

### **Cleaners** (Fix Data)
- `parse_date()` - Dates
- `clean_amount()` - Amounts
- `classify_debit_credit()` - Transaction types

### **Analyzers** (Add Intelligence)
- `classify_credit_revenue()` - Revenue vs deduction
- `calculate_confidence()` - Quality score

### **Builders** (Create Output)
- `_statement_result()` - Final result object

---

## 🎓 Most Important Functions (Top 10)

1. **`process_single_statement()`** - The brain
2. **`detect_pdf_type()`** - Fast-path decision
3. **`extract_digital_pdf()`** - Digital extraction
4. **`extract_ocr_rows()`** - OCR extraction
5. **`map_columns()`** - Structure understanding
6. **`parse_date()`** - Date normalization
7. **`clean_amount()`** - Amount parsing
8. **`classify_debit_credit()`** - Transaction classification
9. **`classify_credit_revenue()`** - Revenue intelligence
10. **`calculate_confidence()`** - Quality assessment

---

## 📈 Performance Impact

| Function | Time | Impact |
|----------|------|--------|
| `detect_pdf_type()` | 50-100ms | **HIGH** - Saves 10-25 sec if digital |
| `extract_digital_pdf()` | 5-15 sec | Fast path |
| `preprocess_scanned_pdf()` | 2-8 sec | Medium |
| `extract_ocr_rows()` | 10-30 sec | Slow path |
| `map_columns()` | <10ms | Negligible |
| `parse_date()` | <1ms | Negligible |
| `clean_amount()` | <1ms | Negligible |

---

## 🔑 Function Selection Guide

**Need to...**

- **Start processing?** → `process_single_statement()`
- **Check PDF type?** → `detect_pdf_type()`
- **Extract digital PDF?** → `extract_digital_pdf()`
- **Prepare scanned image?** → `preprocess_scanned_pdf()`
- **Run OCR?** → `extract_ocr_rows()`
- **Find header?** → `detect_header_row()`
- **Map columns?** → `map_columns()`
- **Parse date?** → `parse_date()`
- **Clean amount?** → `clean_amount()`
- **Classify transaction?** → `classify_debit_credit()`
- **Classify revenue?** → `classify_credit_revenue()`
- **Check duplicate?** → `generate_file_hash()`, `generate_content_hash()`
- **Calculate quality?** → `calculate_confidence()`

---

## 📚 Related Documentation

- **BACKEND_ANALYSIS.md** - Complete technical analysis
- **FUNCTION_REFERENCE.md** - Detailed function documentation
- **OCR_FLOW_SUMMARY.md** - Visual flow diagrams
- **README_BACKEND.md** - Quick start guide

---

*Quick Function Map - All functions at a glance* ⚡
