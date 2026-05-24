# Setup Guide - Bank OCR Service

Complete setup instructions for the Python OCR backend.

## Prerequisites

### 1. Python Version

You need Python 3.10 or 3.11. PaddleOCR does not support Python 3.12 yet.

Check your Python version:
```bash
python --version
```

If you need to install Python:
- Download from: https://www.python.org/downloads/
- Choose version 3.10 or 3.11
- ✅ Check "Add Python to PATH" during installation

### 2. Poppler (Required for PDF processing)

Poppler is needed for converting PDFs to images.

#### Windows Installation:

1. Download Poppler for Windows:
   - Go to: https://github.com/oschwartz10612/poppler-windows/releases
   - Download the latest `Release-XX.XX.X-X.zip`

2. Extract the ZIP file to a location like:
   ```
   C:\Program Files\poppler
   ```

3. Add Poppler to PATH:
   - Open "Environment Variables" (search in Start menu)
   - Under "System variables", find "Path"
   - Click "Edit" → "New"
   - Add: `C:\Program Files\poppler\Library\bin`
   - Click "OK" on all dialogs

4. Verify installation:
   ```bash
   pdftoppm -v
   ```
   You should see version information.

#### Mac Installation:
```bash
brew install poppler
```

#### Linux Installation:
```bash
sudo apt-get install poppler-utils
```

## Step-by-Step Setup

### Step 1: Navigate to Backend Directory

```bash
cd backend-python
```

### Step 2: Create Virtual Environment

```bash
python -m venv venv
```

This creates a `venv` folder with an isolated Python environment.

### Step 3: Activate Virtual Environment

**Windows:**
```bash
venv\Scripts\activate
```

**Mac/Linux:**
```bash
source venv/bin/activate
```

You should see `(venv)` in your terminal prompt.

### Step 4: Install Dependencies

```bash
pip install -r requirements.txt
```

**Important Notes:**
- This will take 5-10 minutes
- PaddleOCR will download ~200MB of models on first run
- If you see warnings about pip version, you can ignore them

**If installation fails:**

Try installing in steps:
```bash
# Install core dependencies first
pip install fastapi uvicorn python-multipart aiofiles python-dotenv

# Install PDF/image processing
pip install PyMuPDF pdfplumber pdf2image pillow

# Install OpenCV and scikit-image
pip install opencv-python-headless scikit-image

# Install PaddlePaddle (CPU version)
pip install paddlepaddle==3.3.1

# Install PaddleOCR
pip install paddleocr==3.5.0

# Install remaining dependencies
pip install pandas beautifulsoup4 lxml numpy
```

### Step 5: Verify Installation

Test that everything is installed:

```bash
python -c "import fastapi, paddleocr, pdfplumber, cv2; print('✅ All dependencies installed!')"
```

If you see the success message, you're ready!

### Step 6: Start the Server

**Option A: Using the start script (Windows)**
```bash
start.bat
```

**Option B: Manual start**
```bash
uvicorn app.main:app --reload --port 8000
```

**First Run:**
- PaddleOCR will download models (~200MB)
- This takes 2-3 minutes
- Don't kill the process - wait for "Application startup complete"

### Step 7: Verify Server is Running

Open your browser and go to:
- http://localhost:8000 - Should show service info
- http://localhost:8000/docs - Interactive API documentation

## Testing the Service

### Test 1: Health Check

```bash
curl http://localhost:8000/api/ocr/health
```

Expected response:
```json
{"status": "ok", "service": "bank-ocr-python"}
```

### Test 2: Process a Statement

Using Swagger UI:
1. Go to http://localhost:8000/docs
2. Click on `POST /api/ocr/process`
3. Click "Try it out"
4. Click "Choose Files" and select a bank statement PDF
5. Click "Execute"
6. Check the response

Using curl:
```bash
curl -X POST http://localhost:8000/api/ocr/process \
  -F "files=@path/to/your/statement.pdf"
```

## Common Issues & Solutions

### Issue 1: "Python not found"

**Solution:**
- Reinstall Python and check "Add to PATH"
- Or use full path: `C:\Python310\python.exe -m venv venv`

### Issue 2: "pip not found"

**Solution:**
```bash
python -m ensurepip --upgrade
```

### Issue 3: "Poppler not found" or "pdftoppm not found"

**Error message:**
```
pdf2image.exceptions.PDFInfoNotInstalledError
```

**Solution:**
- Install Poppler (see Prerequisites section)
- Make sure Poppler's `bin` folder is in PATH
- Restart your terminal after adding to PATH

### Issue 4: PaddleOCR installation fails

**Solution:**
```bash
# Install paddlepaddle first
pip install paddlepaddle==3.3.1 -i https://pypi.tuna.tsinghua.edu.cn/simple

# Then install paddleocr
pip install paddleocr==3.5.0
```

### Issue 5: "Port 8000 already in use"

**Solution:**
```bash
# Use a different port
uvicorn app.main:app --reload --port 8001
```

Or kill the process using port 8000:

**Windows:**
```bash
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

**Mac/Linux:**
```bash
lsof -ti:8000 | xargs kill -9
```

### Issue 6: Low accuracy on scanned PDFs

**Checklist:**
- ✅ Is Poppler installed correctly?
- ✅ Is the PDF actually scanned (not digital)?
- ✅ Is the scan quality good (not too faded)?
- ✅ Check the `confidence` score in response
- ✅ Review `warnings` array in response

**Try:**
- Increase DPI in preprocessing (edit `preprocessor.py`)
- Check if the bank format is supported
- Add new column patterns for your bank

### Issue 7: Server crashes on large files

**Solution:**
- Process files in smaller batches
- Increase timeout in frontend API route
- Add more RAM to your system

## Development Tips

### Auto-reload on Code Changes

The `--reload` flag automatically restarts the server when you edit code:
```bash
uvicorn app.main:app --reload --port 8000
```

### View Logs

Logs are printed to the console. Look for:
- `[INFO]` - Normal operations
- `[WARNING]` - Potential issues
- `[ERROR]` - Failures

### Debug Mode

To see more detailed logs:

Edit `app/main.py`:
```python
logging.basicConfig(
    level=logging.DEBUG,  # Change from INFO to DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### Test Individual Services

You can test services independently:

```python
# Test PDF detection
from app.services.ingestion import detect_pdf_type
from pathlib import Path

pdf_type = detect_pdf_type(Path("test.pdf"))
print(f"PDF Type: {pdf_type}")
```

## Next Steps

After setup is complete:

1. ✅ Test with sample bank statements
2. ✅ Connect frontend (see main README)
3. ✅ Add new bank formats if needed
4. ✅ Monitor accuracy and confidence scores
5. ✅ Optimize for your specific use case

## Production Deployment

For production use:

1. **Remove `--reload` flag:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
   ```

2. **Use a process manager:**
   - Windows: NSSM or Windows Service
   - Linux: systemd or supervisor

3. **Add reverse proxy:**
   - Nginx or Traefik in front of uvicorn

4. **Enable HTTPS:**
   - Use Let's Encrypt certificates

5. **Monitor performance:**
   - Add logging to file
   - Use monitoring tools (Prometheus, Grafana)

6. **Consider GPU:**
   - For high volume, add GPU support
   - Install `paddlepaddle-gpu` instead

## Support

If you encounter issues not covered here:

1. Check the main README.md
2. Review error messages carefully
3. Check Python and Poppler versions
4. Try the step-by-step installation
5. Contact the development team

## Quick Reference

**Start server:**
```bash
cd backend-python
venv\Scripts\activate  # Windows
uvicorn app.main:app --reload --port 8000
```

**Stop server:**
- Press `Ctrl+C` in the terminal

**Reinstall dependencies:**
```bash
pip install -r requirements.txt --force-reinstall
```

**Clear cache:**
```bash
pip cache purge
```

**Update dependencies:**
```bash
pip install -r requirements.txt --upgrade
```
