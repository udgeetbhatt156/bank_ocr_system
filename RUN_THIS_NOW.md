# 🚨 URGENT: Run These Commands Now

## The duplicate detection is now implemented but you need to run the database migration!

---

## Step 1: Run Database Migration (REQUIRED)

Open a terminal and run:

```bash
cd bank-ocr-system
npx prisma migrate dev --name add_duplicate_detection
npx prisma generate
```

This will add the necessary fields to your database:
- `fileHash` - to detect exact file duplicates
- `contentHash` - to detect same content with different files
- `isDuplicate` - flag for duplicate statements
- `duplicateOfId` - reference to original statement

---

## Step 2: Restart Your Services

### Restart Python Service:
```bash
cd backend-python
# Stop the current service (Ctrl+C)
# Then restart:
python -m uvicorn app.main:app --reload --port 8000
```

### Restart Next.js:
```bash
cd bank-ocr-system
# Stop the current service (Ctrl+C)
# Then restart:
npm run dev
```

---

## Step 3: Test Duplicate Detection

1. Upload a bank statement PDF
2. Try to upload the SAME PDF with a different name
3. You should see an error: "Duplicate file detected" or "Duplicate content detected"

---

## What Was Fixed

### Before:
- System only checked filename
- Same PDF with different name = uploaded again ❌
- Created duplicate transactions ❌

### After:
- System checks file hash (SHA-256 of PDF content)
- System checks content hash (hash of extracted transactions)
- Same PDF with different name = BLOCKED ✅
- No duplicate transactions ✅

---

## How It Works Now

```
User uploads "statement_copy.pdf"
    ↓
Python OCR generates file hash
    ↓
Node.js checks database for matching hash
    ↓
If hash exists → ERROR: "Duplicate file detected"
If hash doesn't exist → Process normally
    ↓
After OCR, generate content hash
    ↓
Check database for matching content hash
    ↓
If content hash exists → ERROR: "Duplicate content detected"
If doesn't exist → Save to database
```

---

## Troubleshooting

### Error: "fileHash is not defined"
**Solution:** You didn't run the migration. Run Step 1 above.

### Error: "Python OCR service is not running"
**Solution:** Start the Python service (see Step 2 above).

### Still uploading duplicates?
**Solution:** 
1. Make sure you ran the migration
2. Make sure you restarted both services
3. Check that the Python service is using the new endpoint
4. Clear your browser cache and try again

---

## Verify It's Working

After running the migration and restarting services:

1. Check Python service logs - should show:
   ```
   Generated file hash for statement.pdf: a1b2c3d4...
   Generated content hash: e5f6g7h8...
   ```

2. Try uploading the same file twice - should see error:
   ```
   Error: Duplicate file detected: This exact file was already uploaded as "statement.pdf"
   ```

---

## Need Help?

If you still have issues after running these steps:
1. Check Python service logs for errors
2. Check Next.js console for errors
3. Verify the migration ran successfully: `npx prisma studio` and check Statement table for new fields

---

**🚨 RUN THE MIGRATION NOW! 🚨**
