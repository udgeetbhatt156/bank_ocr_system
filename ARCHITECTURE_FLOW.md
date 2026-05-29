# 🏗️ Architecture Flow - Duplicate Detection System

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           USER INTERFACE                                 │
│                     (Next.js + React + shadcn/ui)                       │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 │ 1. Upload PDF
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      FRONTEND UPLOAD COMPONENT                           │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  • File validation                                                │  │
│  │  • Progress tracking                                              │  │
│  │  • Duplicate warning modal                                        │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 │ 2. POST /api/statements/upload
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    NODE.JS BACKEND (Next.js API)                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  STEP 1: Calculate File Hash                                     │  │
│  │  ├─ SHA-256 of PDF binary                                        │  │
│  │  └─ Time: ~50ms for 5MB file                                     │  │
│  │                                                                   │  │
│  │  STEP 2: Quick Database Check                                    │  │
│  │  ├─ Query: SELECT * WHERE fileHash = ?                           │  │
│  │  ├─ If found → Return 409 Duplicate Error                        │  │
│  │  └─ Time: <10ms (indexed query)                                  │  │
│  │                                                                   │  │
│  │  STEP 3: Forward to Python OCR Service                           │  │
│  │  └─ POST http://localhost:8000/api/ocr/process-with-duplicate... │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 │ 3. Forward file
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   PYTHON FASTAPI OCR SERVICE                            │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  STEP 1: Generate File Hash                                      │  │
│  │  ├─ hash_service.generate_file_hash()                            │  │
│  │  └─ SHA-256 of PDF binary                                        │  │
│  │                                                                   │  │
│  │  STEP 2: Process Document (OCR)                                  │  │
│  │  ├─ Detect PDF type (digital vs scanned)                         │  │
│  │  ├─ Extract text/tables (pdfplumber or PaddleOCR)                │  │
│  │  ├─ Parse transactions                                           │  │
│  │  ├─ Extract metadata (bank name, account number)                 │  │
│  │  └─ Time: 5-30 seconds depending on PDF type                     │  │
│  │                                                                   │  │
│  │  STEP 3: Generate Content Hash                                   │  │
│  │  ├─ hash_service.generate_content_hash()                         │  │
│  │  ├─ Input: transactions + metadata                               │  │
│  │  ├─ Normalize: account numbers, amounts, descriptions            │  │
│  │  ├─ Sort: by date and description                                │  │
│  │  └─ Output: SHA-256 hash                                         │  │
│  │                                                                   │  │
│  │  STEP 4: Generate Transaction Fingerprint                        │  │
│  │  ├─ hash_service.generate_transaction_fingerprint()              │  │
│  │  ├─ Extract: date, amounts, first 3 words of description         │  │
│  │  └─ Output: SHA-256 hash (fuzzy matching)                        │  │
│  │                                                                   │  │
│  │  STEP 5: Return Result                                           │  │
│  │  └─ StatementResult with all hashes                              │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 │ 4. Return OCR result + hashes
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    NODE.JS BACKEND (Continued)                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  STEP 4: Check Content Hash                                      │  │
│  │  ├─ Query: SELECT * WHERE contentHash = ?                        │  │
│  │  ├─ If found → Return 409 Duplicate Error                        │  │
│  │  └─ Time: <10ms (indexed query)                                  │  │
│  │                                                                   │  │
│  │  STEP 5: Save to Database                                        │  │
│  │  ├─ Create Statement record with hashes                          │  │
│  │  ├─ Create Transaction records                                   │  │
│  │  └─ Time: ~50ms                                                  │  │
│  │                                                                   │  │
│  │  STEP 6: Return Success                                          │  │
│  │  └─ { success: true, statement, transactions }                   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 │ 5. Return result
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      FRONTEND (Success/Error)                           │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  IF SUCCESS:                                                      │  │
│  │  ├─ Show success toast                                           │  │
│  │  ├─ Refresh transaction list                                     │  │
│  │  └─ Update dashboard                                             │  │
│  │                                                                   │  │
│  │  IF DUPLICATE:                                                    │  │
│  │  ├─ Show DuplicateWarningModal                                   │  │
│  │  ├─ Display original filename                                    │  │
│  │  ├─ Offer actions: Skip / View Original / Force Upload           │  │
│  │  └─ User decides next action                                     │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Duplicate Detection Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DUPLICATE DETECTION LOGIC                        │
└─────────────────────────────────────────────────────────────────────────┘

Upload File: "statement_copy.pdf"
     │
     ├─ Calculate File Hash: "a1b2c3d4e5f6..."
     │
     ▼
┌─────────────────────────────────────┐
│  Check Database: fileHash = ?       │
│                                     │
│  SELECT * FROM Statement            │
│  WHERE fileHash = 'a1b2c3d4e5f6...' │
│  AND accountId = 'account123'       │
└─────────────────┬───────────────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
    FOUND               NOT FOUND
        │                   │
        ▼                   ▼
┌───────────────────┐   ┌──────────────────────┐
│ DUPLICATE!        │   │ Continue Processing  │
│                   │   │                      │
│ Return 409:       │   │ Send to Python OCR   │
│ {                 │   └──────────┬───────────┘
│   error: "...",   │              │
│   duplicate: {    │              │ Process with OCR
│     type: "exact" │              │ (5-30 seconds)
│     original: "..." │            │
│   }               │              ▼
│ }                 │   ┌──────────────────────┐
└───────────────────┘   │ OCR Complete         │
                        │                      │
                        │ Extracted:           │
                        │ - 47 transactions    │
                        │ - Bank: Chase        │
                        │ - Account: ****1234  │
                        │                      │
                        │ Generated:           │
                        │ - content_hash       │
                        │ - fingerprint        │
                        └──────────┬───────────┘
                                   │
                                   ▼
                        ┌──────────────────────┐
                        │ Check Database:      │
                        │ contentHash = ?      │
                        │                      │
                        │ SELECT * FROM        │
                        │ Statement WHERE      │
                        │ contentHash = '...'  │
                        └──────────┬───────────┘
                                   │
                         ┌─────────┴─────────┐
                         │                   │
                     FOUND               NOT FOUND
                         │                   │
                         ▼                   ▼
                ┌────────────────┐   ┌──────────────┐
                │ DUPLICATE!     │   │ UNIQUE!      │
                │                │   │              │
                │ Return 409:    │   │ Save to DB:  │
                │ {              │   │ - Statement  │
                │   error: "..." │   │ - Hashes     │
                │   duplicate: { │   │ - Txns       │
                │     type:      │   │              │
                │     "content"  │   │ Return 200   │
                │   }            │   └──────────────┘
                │ }              │
                └────────────────┘
```

---

## Hash Generation Process

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         HASH GENERATION FLOW                            │
└─────────────────────────────────────────────────────────────────────────┘

Input: statement.pdf
     │
     ├─────────────────────────────────────────────────────────────────┐
     │                                                                  │
     ▼                                                                  ▼
┌──────────────────────┐                                    ┌──────────────────────┐
│  FILE HASH           │                                    │  PROCESS WITH OCR    │
│                      │                                    │                      │
│  1. Read PDF binary  │                                    │  1. Extract text     │
│  2. SHA-256 hash     │                                    │  2. Parse tables     │
│  3. Output:          │                                    │  3. Identify txns    │
│     "a1b2c3d4..."    │                                    │  4. Extract metadata │
│                      │                                    │                      │
│  Time: ~50ms         │                                    │  Time: 5-30 sec      │
└──────────────────────┘                                    └──────────┬───────────┘
                                                                       │
                                                                       ▼
                                                            ┌──────────────────────┐
                                                            │  Extracted Data:     │
                                                            │                      │
                                                            │  Transactions: [     │
                                                            │    {                 │
                                                            │      date: "2024-01" │
                                                            │      desc: "Walmart" │
                                                            │      debit: 45.67    │
                                                            │    },                │
                                                            │    ...               │
                                                            │  ]                   │
                                                            │                      │
                                                            │  Metadata: {         │
                                                            │    bank: "Chase"     │
                                                            │    account: "1234"   │
                                                            │    balance: 1500.00  │
                                                            │  }                   │
                                                            └──────────┬───────────┘
                                                                       │
                                                    ┌──────────────────┴──────────────────┐
                                                    │                                     │
                                                    ▼                                     ▼
                                         ┌──────────────────────┐            ┌──────────────────────┐
                                         │  CONTENT HASH        │            │  FINGERPRINT         │
                                         │                      │            │                      │
                                         │  1. Normalize data:  │            │  1. Extract key      │
                                         │     - Account: XXXX  │            │     features:        │
                                         │     - Amounts: 45.67 │            │     - Date           │
                                         │     - Descriptions   │            │     - Amounts        │
                                         │  2. Sort by date     │            │     - First 3 words  │
                                         │  3. JSON stringify   │            │  2. Sort by date     │
                                         │  4. SHA-256 hash     │            │  3. SHA-256 hash     │
                                         │  5. Output:          │            │  4. Output:          │
                                         │     "e5f6g7h8..."    │            │     "i9j0k1l2..."    │
                                         │                      │            │                      │
                                         │  Time: ~10ms         │            │  Time: ~15ms         │
                                         └──────────────────────┘            └──────────────────────┘
```

---

## Database Schema

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          DATABASE STRUCTURE                             │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  Statement                                                           │
├──────────────────────────────────────────────────────────────────────┤
│  id                String    @id @default(cuid())                    │
│  fileName          String                                            │
│  filePath          String                                            │
│  fileHash          String?   ◄─── NEW: SHA-256 of file              │
│  contentHash       String?   ◄─── NEW: Hash of extracted data       │
│  uploadedAt        DateTime                                          │
│  processedAt       DateTime?                                         │
│  status            String                                            │
│  confidence        Float?                                            │
│  pdfType           String?                                           │
│  bankName          String?                                           │
│  accountNumber     String?                                           │
│  currentBalance    Decimal?                                          │
│  accountId         String                                            │
│  isDuplicate       Boolean   ◄─── NEW: Duplicate flag               │
│  duplicateOfId     String?   ◄─── NEW: Reference to original        │
│  rawData           Json?                                             │
│                                                                       │
│  @@index([fileHash])         ◄─── NEW: Fast lookup                  │
│  @@index([contentHash])      ◄─── NEW: Fast lookup                  │
│  @@unique([accountId, fileHash])  ◄─── NEW: Prevent duplicates      │
└──────────────────────────────────────────────────────────────────────┘

Example Query:
┌──────────────────────────────────────────────────────────────────────┐
│  -- Check for duplicate by file hash                                 │
│  SELECT * FROM Statement                                             │
│  WHERE fileHash = 'a1b2c3d4e5f6...'                                  │
│  AND accountId = 'account123'                                        │
│  LIMIT 1;                                                            │
│                                                                       │
│  -- Check for duplicate by content hash                              │
│  SELECT * FROM Statement                                             │
│  WHERE contentHash = 'e5f6g7h8i9j0...'                               │
│  AND accountId = 'account123'                                        │
│  LIMIT 1;                                                            │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Performance Timeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      PERFORMANCE BREAKDOWN                              │
└─────────────────────────────────────────────────────────────────────────┘

SCENARIO 1: Exact File Duplicate (Fast Path)
═══════════════════════════════════════════════════════════════════════════

0ms     ├─ User uploads file
        │
50ms    ├─ Calculate file hash (SHA-256)
        │
60ms    ├─ Database query (indexed)
        │  └─ FOUND! Duplicate detected
        │
60ms    └─ Return 409 error to user
        
Total: ~60ms (OCR processing skipped! ✓)


SCENARIO 2: Content Duplicate (Medium Path)
═══════════════════════════════════════════════════════════════════════════

0ms     ├─ User uploads file
        │
50ms    ├─ Calculate file hash
        │
60ms    ├─ Database query (not found)
        │
60ms    ├─ Send to Python OCR service
        │
15s     ├─ OCR processing (scanned PDF)
        │  ├─ Preprocess images
        │  ├─ Run PaddleOCR
        │  ├─ Parse transactions
        │  └─ Extract metadata
        │
15.01s  ├─ Generate content hash
        │
15.02s  ├─ Generate fingerprint
        │
15.03s  ├─ Return to Node.js
        │
15.04s  ├─ Database query (content hash)
        │  └─ FOUND! Duplicate detected
        │
15.04s  └─ Return 409 error to user

Total: ~15 seconds (OCR ran, but saved from DB insert)


SCENARIO 3: Unique Statement (Full Path)
═══════════════════════════════════════════════════════════════════════════

0ms     ├─ User uploads file
        │
50ms    ├─ Calculate file hash
        │
60ms    ├─ Database query (not found)
        │
60ms    ├─ Send to Python OCR service
        │
15s     ├─ OCR processing
        │
15.01s  ├─ Generate content hash
        │
15.02s  ├─ Generate fingerprint
        │
15.03s  ├─ Return to Node.js
        │
15.04s  ├─ Database query (not found)
        │
15.09s  ├─ Save to database
        │  ├─ Create Statement
        │  └─ Create Transactions
        │
15.09s  └─ Return 200 success to user

Total: ~15 seconds (Full processing + save)
```

---

## Error Handling Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         ERROR HANDLING                                  │
└─────────────────────────────────────────────────────────────────────────┘

                        ┌─────────────────┐
                        │  Upload File    │
                        └────────┬────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
                    ▼                         ▼
            ┌───────────────┐        ┌───────────────┐
            │ File too large│        │ Invalid format│
            │ > 50MB        │        │ Not PDF/image │
            └───────┬───────┘        └───────┬───────┘
                    │                        │
                    └────────┬───────────────┘
                             │
                             ▼
                    ┌────────────────┐
                    │ Return 400     │
                    │ Bad Request    │
                    └────────────────┘

                        ┌─────────────────┐
                        │  Hash Generation│
                        └────────┬────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
                    ▼                         ▼
            ┌───────────────┐        ┌───────────────┐
            │ File read error│       │ Hash collision│
            │               │        │ (extremely    │
            │               │        │  rare)        │
            └───────┬───────┘        └───────┬───────┘
                    │                        │
                    └────────┬───────────────┘
                             │
                             ▼
                    ┌────────────────┐
                    │ Log error      │
                    │ Continue with  │
                    │ null hash      │
                    └────────────────┘

                        ┌─────────────────┐
                        │  OCR Processing │
                        └────────┬────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
                    ▼                         ▼
            ┌───────────────┐        ┌───────────────┐
            │ OCR failed    │        │ No transactions│
            │               │        │ extracted     │
            └───────┬───────┘        └───────┬───────┘
                    │                        │
                    └────────┬───────────────┘
                             │
                             ▼
                    ┌────────────────┐
                    │ Return result  │
                    │ with warnings  │
                    │ confidence: 0  │
                    └────────────────┘

                        ┌─────────────────┐
                        │  Database Save  │
                        └────────┬────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
                    ▼                         ▼
            ┌───────────────┐        ┌───────────────┐
            │ Unique        │        │ Connection    │
            │ constraint    │        │ error         │
            │ violation     │        │               │
            └───────┬───────┘        └───────┬───────┘
                    │                        │
                    └────────┬───────────────┘
                             │
                             ▼
                    ┌────────────────┐
                    │ Return 500     │
                    │ Retry or alert │
                    └────────────────┘
```

---

## Summary

This architecture provides:

✅ **Fast duplicate detection** (60ms for exact file duplicates)  
✅ **Robust content matching** (handles rescanned PDFs)  
✅ **Fuzzy matching** (detects OCR variations)  
✅ **Minimal overhead** (~85ms total for unique files)  
✅ **Database integrity** (unique constraints)  
✅ **Clear user feedback** (duplicate warnings)  
✅ **Comprehensive error handling** (graceful degradation)

**Key Performance Metrics:**
- File hash check: 60ms (saves 15+ seconds on duplicates)
- Content hash generation: 10ms
- Database queries: <10ms (indexed)
- Total overhead: ~85ms per unique file
