# 🚀 Quick Start Guide - Duplicate Detection

## For Developers: Get Started in 5 Minutes

---

## 📋 **What Was Implemented**

A **multi-layered duplicate detection system** that prevents the same bank statement from being uploaded multiple times with different filenames.

**Detection Methods:**
1. **File Hash** - Detects exact file copies
2. **Content Hash** - Detects same content (rescanned PDFs)
3. **Transaction Fingerprint** - Detects near-duplicates with OCR variations

---

## 🎯 **Quick Implementation Checklist**

### ✅ **Step 1: Database Migration** (2 minutes)

```bash
cd bank-ocr-system
npx prisma migrate dev --name add_duplicate_detection
npx prisma generate
```

This adds the following fields to the `Statement` model:
- `fileHash` - SHA-256 of file content
- `contentHash` - Hash of extracted data
- `isDuplicate` - Boolean flag
- `duplicateOfId` - Reference to original statement

---

### ✅ **Step 2: Test Python Service** (3 minutes)

```bash
# Start the Python service
cd backend-python
python -m uvicorn app.main:app --reload --port 8000

# Test the new endpoint
curl -X POST "http://localhost:8000/api/ocr/process-with-duplicate-check" \
  -F "files=@path/to/test_statement.pdf"
```

**Expected Response:**
```json
{
  "status": "success",
  "documents": [{
    "filename": "test_statement.pdf",
    "file_hash": "a1b2c3d4e5f6...",
    "content_hash": "g7h8i9j0k1l2...",
    "fingerprint": "m3n4o5p6q7r8...",
    "transactions": [...],
    "is_duplicate": false
  }]
}
```

---

### ⬜ **Step 3: Backend Integration** (Node.js/Next.js)

Create a new API route or update existing upload handler:

```typescript
// app/api/statements/upload/route.ts

import { prisma } from '@/lib/prisma';
import crypto from 'crypto';

export async function POST(request: Request) {
  const formData = await request.formData();
  const file = formData.get('file') as File;
  const accountId = formData.get('accountId') as string;
  
  // Step 1: Calculate file hash
  const buffer = await file.arrayBuffer();
  const fileHash = crypto
    .createHash('sha256')
    .update(Buffer.from(buffer))
    .digest('hex');
  
  // Step 2: Check for exact file duplicate
  const existingFile = await prisma.statement.findFirst({
    where: { 
      fileHash: fileHash,
      accountId: accountId 
    }
  });
  
  if (existingFile) {
    return Response.json({
      error: 'Duplicate file detected',
      duplicate: {
        type: 'exact_file',
        original: existingFile.fileName,
        message: 'This exact file has been uploaded before'
      }
    }, { status: 409 });
  }
  
  // Step 3: Send to Python OCR service
  const ocrFormData = new FormData();
  ocrFormData.append('files', file);
  
  const ocrResponse = await fetch(
    'http://localhost:8000/api/ocr/process-with-duplicate-check',
    { method: 'POST', body: ocrFormData }
  );
  
  const ocrResult = await ocrResponse.json();
  const document = ocrResult.documents[0];
  
  // Step 4: Check for content duplicate
  const existingContent = await prisma.statement.findFirst({
    where: { 
      contentHash: document.content_hash,
      accountId: accountId 
    }
  });
  
  if (existingContent) {
    return Response.json({
      error: 'Duplicate content detected',
      duplicate: {
        type: 'exact_content',
        original: existingContent.fileName,
        message: 'This statement content has been processed before'
      }
    }, { status: 409 });
  }
  
  // Step 5: Save to database
  const statement = await prisma.statement.create({
    data: {
      fileName: file.name,
      fileHash: fileHash,
      contentHash: document.content_hash,
      accountId: accountId,
      confidence: document.confidence,
      pdfType: document.pdf_type,
      bankName: document.bank_name,
      accountNumber: document.account_number,
      currentBalance: document.current_balance,
      status: 'completed',
      processedAt: new Date(),
    }
  });
  
  // Step 6: Save transactions
  const transactions = await prisma.transaction.createMany({
    data: document.transactions.map(txn => ({
      statementId: statement.id,
      accountId: accountId,
      date: new Date(txn.date),
      description: txn.description,
      debit: txn.debit,
      credit: txn.credit,
      balance: txn.balance,
      reference: txn.reference,
      sourceLine: txn.source_line,
    }))
  });
  
  return Response.json({
    success: true,
    statement: statement,
    transactionCount: transactions.count
  });
}
```

---

### ⬜ **Step 4: Frontend Integration**

Create a duplicate warning modal:

```typescript
// components/DuplicateWarningModal.tsx

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircle } from "lucide-react";

interface DuplicateWarningModalProps {
  isOpen: boolean;
  duplicate: {
    type: string;
    original: string;
    message: string;
  };
  onSkip: () => void;
  onViewOriginal: () => void;
  onForceUpload?: () => void;
}

export function DuplicateWarningModal({
  isOpen,
  duplicate,
  onSkip,
  onViewOriginal,
  onForceUpload
}: DuplicateWarningModalProps) {
  return (
    <Dialog open={isOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-yellow-500" />
            Duplicate Statement Detected
          </DialogTitle>
          <DialogDescription>
            {duplicate.message}
          </DialogDescription>
        </DialogHeader>
        
        <Alert variant="default" className="border-yellow-500">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Original File</AlertTitle>
          <AlertDescription>
            <span className="font-semibold">{duplicate.original}</span>
            <br />
            <span className="text-sm text-muted-foreground">
              Uploaded previously
            </span>
          </AlertDescription>
        </Alert>
        
        <div className="flex flex-col gap-2">
          <Button onClick={onSkip} className="w-full">
            Skip This Upload
          </Button>
          <Button 
            variant="outline" 
            onClick={onViewOriginal}
            className="w-full"
          >
            View Original Statement
          </Button>
          {onForceUpload && (
            <Button 
              variant="destructive" 
              onClick={onForceUpload}
              className="w-full"
            >
              Force Upload Anyway
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

Update your upload page:

```typescript
// app/(dashboard)/upload/page.tsx

'use client';

import { useState } from 'react';
import { DuplicateWarningModal } from '@/components/DuplicateWarningModal';

export default function UploadPage() {
  const [duplicateInfo, setDuplicateInfo] = useState(null);
  const [showDuplicateModal, setShowDuplicateModal] = useState(false);
  
  async function handleFileUpload(file: File) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('accountId', currentAccountId);
    
    const response = await fetch('/api/statements/upload', {
      method: 'POST',
      body: formData
    });
    
    const result = await response.json();
    
    if (result.error && result.duplicate) {
      // Duplicate detected
      setDuplicateInfo(result.duplicate);
      setShowDuplicateModal(true);
    } else if (result.success) {
      // Success - refresh transaction list
      toast.success(`Uploaded ${file.name} successfully`);
      refreshTransactions();
    }
  }
  
  return (
    <div>
      {/* Your upload UI */}
      <FileUploadZone onUpload={handleFileUpload} />
      
      {/* Duplicate warning modal */}
      <DuplicateWarningModal
        isOpen={showDuplicateModal}
        duplicate={duplicateInfo}
        onSkip={() => setShowDuplicateModal(false)}
        onViewOriginal={() => {
          // Navigate to original statement
          router.push(`/statements/${duplicateInfo.originalId}`);
        }}
        onForceUpload={() => {
          // Implement force upload logic if needed
          setShowDuplicateModal(false);
        }}
      />
    </div>
  );
}
```

---

## 🧪 **Testing**

### Test Case 1: Exact File Duplicate

```bash
# Upload a statement
curl -X POST "http://localhost:3000/api/statements/upload" \
  -F "file=@statement_jan.pdf" \
  -F "accountId=account123"

# Upload the same file with different name
curl -X POST "http://localhost:3000/api/statements/upload" \
  -F "file=@statement_jan_copy.pdf" \
  -F "accountId=account123"

# Expected: 409 Conflict with duplicate error
```

### Test Case 2: Different Statements

```bash
# Upload January statement
curl -X POST "http://localhost:3000/api/statements/upload" \
  -F "file=@statement_jan.pdf" \
  -F "accountId=account123"

# Upload February statement
curl -X POST "http://localhost:3000/api/statements/upload" \
  -F "file=@statement_feb.pdf" \
  -F "accountId=account123"

# Expected: Both succeed, no duplicate detected
```

---

## 📊 **Database Queries**

### Check for duplicates manually:

```sql
-- Find all statements with duplicates
SELECT 
  s1.id,
  s1.fileName,
  s1.fileHash,
  s2.fileName as duplicate_of
FROM Statement s1
JOIN Statement s2 ON s1.fileHash = s2.fileHash AND s1.id != s2.id
WHERE s1.accountId = 'account123';

-- Find statements by content hash
SELECT fileName, contentHash, uploadedAt
FROM Statement
WHERE contentHash = 'abc123...'
ORDER BY uploadedAt;
```

---

## 🐛 **Troubleshooting**

### Issue: "fileHash is not defined"
**Solution:** Run the database migration:
```bash
npx prisma migrate dev --name add_duplicate_detection
```

### Issue: "Module not found: hash_service"
**Solution:** Ensure the new Python files are in the correct location:
- `backend-python/app/services/hash_service.py`
- `backend-python/app/services/duplicate_detector.py`

### Issue: "Duplicate not detected"
**Solution:** Check that you're using the new endpoint:
- Use `/api/ocr/process-with-duplicate-check` (not `/api/ocr/process`)

### Issue: "False positives"
**Solution:** Adjust similarity threshold in `duplicate_detector.py`:
```python
SIMILARITY_THRESHOLD = 0.95  # Increase to 0.98 for stricter matching
```

---

## 📚 **Additional Resources**

- **Full Documentation:** `DUPLICATE_DETECTION.md`
- **Implementation Summary:** `IMPLEMENTATION_SUMMARY.md`
- **Code Comments:** Check inline comments in service files

---

## ✅ **Verification Checklist**

- [ ] Database migration completed
- [ ] Python service starts without errors
- [ ] New endpoint returns hash values
- [ ] Backend API checks for duplicates
- [ ] Frontend shows duplicate warning
- [ ] Test cases pass
- [ ] Duplicate statements are blocked
- [ ] Unique statements are processed normally

---

## 🎉 **You're Done!**

The duplicate detection system is now active. Users will be warned when uploading duplicate statements, preventing duplicate transactions in the database.

**Next Steps:**
1. Test with real bank statements
2. Monitor logs for any issues
3. Gather user feedback
4. Consider implementing batch duplicate detection

---

**Questions?** Review the detailed documentation in `DUPLICATE_DETECTION.md`
