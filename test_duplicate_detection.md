# Test Duplicate Detection

## Quick Test Steps

### 1. Run Migration First!
```bash
cd bank-ocr-system
npx prisma migrate dev --name add_duplicate_detection
npx prisma generate
```

### 2. Restart Services
```bash
# Terminal 1 - Python Service
cd backend-python
python -m uvicorn app.main:app --reload --port 8000

# Terminal 2 - Next.js
cd bank-ocr-system
npm run dev
```

### 3. Test Duplicate Detection

#### Test A: Upload Same File Twice
1. Go to http://localhost:3000/upload
2. Upload a bank statement PDF (e.g., `statement.pdf`)
3. Wait for it to process successfully
4. Try to upload the SAME file again (even with a different name like `statement_copy.pdf`)
5. **Expected Result:** Error message saying "Duplicate file detected"

#### Test B: Upload Different Files
1. Upload `january_statement.pdf`
2. Upload `february_statement.pdf`
3. **Expected Result:** Both should upload successfully (no duplicate error)

---

## What to Look For

### Success Indicators:
✅ First upload works normally
✅ Second upload of same file shows error
✅ Error message mentions "Duplicate file detected" or "Duplicate content detected"
✅ No duplicate transactions in database

### Python Service Logs Should Show:
```
INFO: Generated file hash for statement.pdf: a1b2c3d4e5f6...
INFO: Generated content hash: e5f6g7h8i9j0...
```

### Browser Console Should Show:
```
Error: Duplicate file detected: This exact file was already uploaded as "statement.pdf"
```

---

## If It's Not Working

### Check 1: Did you run the migration?
```bash
cd bank-ocr-system
npx prisma studio
```
Open the Statement table and check if you see `fileHash` and `contentHash` columns.

### Check 2: Is Python service using the new endpoint?
Check Python logs - should see:
```
INFO: [statement.pdf] Generated file hash...
```

### Check 3: Is Next.js calling the right endpoint?
Check Next.js logs - should see:
```
POST /api/ocr/process-with-duplicate-check
```

### Check 4: Are services restarted?
Make sure you restarted BOTH services after running the migration.

---

## Manual Database Check

After uploading a file, check the database:

```bash
cd bank-ocr-system
npx prisma studio
```

1. Open `Statement` table
2. Find your uploaded statement
3. Check that `fileHash` and `contentHash` fields have values (long hex strings)
4. Try uploading the same file again
5. Should get error before a new row is created

---

## Debugging

### If you see: "fileHash is not defined"
- You didn't run the migration
- Run: `npx prisma migrate dev --name add_duplicate_detection`

### If duplicates still upload:
- Check that Python service is running on port 8000
- Check that Next.js is calling `/api/ocr/process-with-duplicate-check`
- Check Python logs for hash generation
- Clear browser cache and try again

### If you see: "Cannot connect to Python service"
- Start Python service: `cd backend-python && python -m uvicorn app.main:app --reload --port 8000`

---

## Expected Flow

```
1. User uploads "statement.pdf"
   → Python generates hashes
   → Saves to DB with hashes
   → Success ✅

2. User uploads "statement_copy.pdf" (same file, different name)
   → Python generates hashes
   → Node.js checks DB: fileHash matches!
   → Error: "Duplicate file detected" ❌
   → No new record created ✅

3. User uploads "february_statement.pdf" (different file)
   → Python generates hashes
   → Node.js checks DB: no match
   → Saves to DB
   → Success ✅
```

---

## Success Criteria

✅ Same file with different name is blocked
✅ Different files upload successfully
✅ Error message is clear and helpful
✅ No duplicate transactions in database
✅ Original file information is shown in error

---

**Ready to test? Run the migration first!**
