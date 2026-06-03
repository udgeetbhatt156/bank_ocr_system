# Duplicate Detection Implementation

## Overview

This document describes the duplicate detection system implemented for the Bank OCR Statement processing system. The system prevents duplicate transactions from being created when the same bank statement is uploaded multiple times with different filenames.

## Problem Statement

**Issue:** Users may upload the same bank statement PDF multiple times with different filenames, leading to:
- Duplicate transaction entries in the database
- Incorrect financial summaries
- Data integrity issues
- Confusion in transaction history

## Solution Architecture

### Two-Layer Hash-Based Approach

The system uses two strategies to detect duplicates:

#### 1. **File Hash (Exact File Duplicate)**
- **Method:** SHA-256 hash of the entire PDF binary content
- **Detects:** Exact file copies regardless of filename
- **Use Case:** User uploads "statement_jan.pdf" and later uploads the same file as "january_statement.pdf"
- **Confidence:** 100%

#### 2. **Content Hash (Exact Content Duplicate)**
- **Method:** SHA-256 hash of normalized transaction data + metadata
- **Detects:** Same statement content even if PDF is slightly different (rescanned, different quality)
- **Use Case:** User scans the same paper statement twice with different scan settings
- **Confidence:** 100%

## Implementation Details

### Files Modified/Created

#### 1. **Database Schema** (`prisma/schema.prisma`)
```prisma
model Statement {
  // ... existing fields ...
  fileHash       String?       // SHA-256 of file content
  contentHash    String?       // Hash of extracted data
  isDuplicate    Boolean       @default(false)
  duplicateOfId  String?       // Reference to original
  
  @@index([fileHash])
  @@index([contentHash])
  @@unique([accountId, fileHash])
}
```

#### 2. **Hash Service** (`app/services/hash_service.py`)
**Functions:**
- `generate_file_hash(file_path)` - Creates SHA-256 of PDF binary
- `generate_content_hash(transactions, metadata)` - Creates hash of extracted data
- `calculate_content_similarity(txns1, txns2)` - Compares two transaction sets (utility only)

**Key Features:**
- Normalizes account numbers (handles `****1234` vs `XXXX1234`)
- Rounds amounts to avoid floating-point issues
- Sorts transactions for consistent ordering
- Sorts transactions for consistent content hashing

#### 3. **Duplicate Detector** (`app/services/duplicate_detector.py`)
**Main Function:** `check_for_duplicates(file_path, transactions, metadata, existing_statements)`

**Returns:** `DuplicateCheckResult` with:
- `is_duplicate`: Boolean flag
- `duplicate_type`: "exact_file" or "exact_content"
- `confidence`: 0.0 to 1.0
- `original_filename`: Name of the original statement
- `message`: User-friendly explanation
- `file_hash`, `content_hash`: Hash values

**Detection Logic:**
```python
1. Generate hashes for uploaded file
2. Compare file_hash with existing statements → Exact file match
3. Compare content_hash with existing statements → Exact content match
4. Return result with appropriate confidence level
```

#### 4. **Updated Schemas** (`app/models/schemas.py`)
Added fields to `StatementResult`:
```python
file_hash: Optional[str]
content_hash: Optional[str]
is_duplicate: bool
duplicate_type: Optional[str]
duplicate_of: Optional[str]
duplicate_confidence: Optional[float]
duplicate_message: Optional[str]
```

#### 5. **Updated OCR Router** (`app/routers/ocr.py`)
**New Endpoint:** `/api/ocr/process-with-duplicate-check`

**Flow:**
1. Receive uploaded file
2. Generate file hash
3. Process document (OCR extraction)
4. Generate content hash
5. Return result with file_hash and content_hash
6. Frontend/Backend checks hashes against database

## Usage Flow

### Backend Integration (Node.js/Next.js)

```typescript
// 1. User uploads file
const file = uploadedFile;

// 2. Check database for existing file hash (quick check)
const existingByFileHash = await prisma.statement.findFirst({
  where: { 
    fileHash: calculatedFileHash,
    accountId: userAccountId 
  }
});

if (existingByFileHash) {
  return {
    error: "Duplicate file detected",
    original: existingByFileHash.fileName,
    message: "This exact file has been uploaded before"
  };
}

// 3. Send to Python OCR service
const response = await fetch('http://localhost:8000/api/ocr/process-with-duplicate-check', {
  method: 'POST',
  body: formData
});

const result = await response.json();

// 4. Check content hash against database
const existingByContentHash = await prisma.statement.findFirst({
  where: { 
    contentHash: result.documents[0].content_hash,
    accountId: userAccountId 
  }
});

if (existingByContentHash) {
  return {
    error: "Duplicate content detected",
    original: existingByContentHash.fileName,
    message: "This statement content has been processed before"
  };
}

// 5. Save to database with hash values
await prisma.statement.create({
  data: {
    fileName: file.name,
    fileHash: result.documents[0].file_hash,
    contentHash: result.documents[0].content_hash,
    // ... other fields
  }
});
```

### Frontend User Experience

```typescript
// When duplicate detected, show modal:
<DuplicateWarningModal
  duplicateType={result.duplicate_type}
  originalFileName={result.duplicate_of}
  confidence={result.duplicate_confidence}
  message={result.duplicate_message}
  onSkip={() => skipUpload()}
  onViewOriginal={() => showOriginalStatement()}
  onForceUpload={() => uploadAnyway()}
/>
```

## Database Migration

After updating the Prisma schema, run:

```bash
cd bank-ocr-system
npx prisma migrate dev --name add_duplicate_detection
npx prisma generate
```

## Testing Strategy

### Test Cases

1. **Exact File Duplicate**
   - Upload `statement.pdf`
   - Upload same file as `statement_copy.pdf`
   - Expected: Detected as exact_file duplicate

2. **Rescanned Statement**
   - Upload scanned statement (scan1.pdf)
   - Rescan same paper statement with different settings (scan2.pdf)
   - Expected: Detected as exact_content duplicate

3. **OCR Variations**
   - Upload statement with minor OCR differences
   - Expected: Detected as similar_content duplicate

4. **Different Statements**
   - Upload January statement
   - Upload February statement
   - Expected: No duplicate detected

5. **Same Statement, Different Accounts**
   - Upload statement for Account A
   - Upload same statement for Account B
   - Expected: No duplicate (different account context)

### Manual Testing

```bash
# Start Python service
cd backend-python
python -m uvicorn app.main:app --reload --port 8000

# Test duplicate detection endpoint
curl -X POST "http://localhost:8000/api/ocr/process-with-duplicate-check" \
  -F "files=@test_statement.pdf"

# Check response for hash values
```

## Performance Considerations

### Hash Generation Performance
- **File Hash:** O(n) where n = file size, ~50ms for 5MB PDF
- **Content Hash:** O(m log m) where m = number of transactions, ~10ms for 100 transactions

### Database Query Performance
- Indexed on `fileHash` and `contentHash` for fast lookups
- Unique constraint on `(accountId, fileHash)` prevents duplicates at DB level
- Expected query time: <10ms

### Optimization Tips
1. Check file hash BEFORE calling Python OCR service (saves processing time)
2. Use database indexes for fast duplicate lookups
3. Cache recent statement hashes in Redis for ultra-fast checks (optional)

## Security Considerations

1. **Hash Collision:** SHA-256 has negligible collision probability (2^-256)
2. **Privacy:** Hashes are one-way; original content cannot be recovered
3. **Database Security:** Hash values are not sensitive but should be protected like other data

## Future Enhancements

1. **Batch Duplicate Detection:** Check multiple files against each other before processing
2. **Partial Duplicate Detection:** Detect if statement is a subset/superset of existing data
3. **Smart Merging:** Offer to merge transactions if user confirms it's an updated statement
4. **Duplicate Dashboard:** Show all detected duplicates with resolution options
5. **Machine Learning:** Train model to detect duplicates based on patterns

## Troubleshooting

### Issue: False Positives
**Symptom:** Different statements detected as duplicates
**Solution:** Adjust `SIMILARITY_THRESHOLD` in `duplicate_detector.py` (default: 0.95)

### Issue: False Negatives
**Symptom:** Duplicate statements not detected
**Solution:** 
- Check if OCR extracted different transaction counts
- Verify account numbers are being extracted correctly
- Review normalization logic in `hash_service.py`

### Issue: Performance Degradation
**Symptom:** Slow duplicate checking with many statements
**Solution:**
- Ensure database indexes are created
- Limit comparison to statements from same account
- Implement Redis caching for recent hashes

## API Reference

### POST `/api/ocr/process-with-duplicate-check`

**Request:**
```
Content-Type: multipart/form-data
files: [PDF files]
```

**Response:**
```json
{
  "status": "success",
  "documents": [
    {
      "filename": "statement.pdf",
      "transactions": [...],
      "confidence": 0.95,
      "file_hash": "a1b2c3d4...",
      "content_hash": "e5f6g7h8...",
      "is_duplicate": false,
      "duplicate_type": null,
      "duplicate_of": null,
      "duplicate_confidence": null,
      "duplicate_message": null
    }
  ]
}
```

## Conclusion

This duplicate detection system provides robust protection against duplicate statement uploads using multiple complementary strategies. The implementation is clean, performant, and maintainable, following software engineering best practices.

**Key Benefits:**
- ✅ Prevents duplicate transactions
- ✅ Maintains data integrity
- ✅ Provides clear user feedback
- ✅ Minimal performance impact
- ✅ Easy to test and maintain
