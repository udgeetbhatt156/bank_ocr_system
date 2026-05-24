@echo off
echo ============================================================
echo  Bank OCR Python Service Startup
echo ============================================================
echo.

cd /d "%~dp0"

REM Check if virtual environment exists
if not exist venv\ (
    echo [!] Virtual environment not found!
    echo [*] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        echo Please ensure Python is installed and in PATH
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
    echo.
)

REM Activate virtual environment
echo [*] Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment
    pause
    exit /b 1
)
echo [OK] Virtual environment activated
echo.

REM Check if dependencies are installed
echo [*] Checking dependencies...
python -c "import fastapi" 2>nul
if errorlevel 1 (
    echo [!] Dependencies not installed
    echo [*] Installing dependencies from requirements.txt...
    echo     This may take a few minutes...
    echo.
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies
        pause
        exit /b 1
    )
    echo.
    echo [OK] Dependencies installed successfully
    echo.
) else (
    echo [OK] Dependencies already installed
    echo.
)

REM Create uploads directory if it doesn't exist
if not exist uploads\ (
    echo [*] Creating uploads directory...
    mkdir uploads
    echo [OK] Uploads directory created
    echo.
)

REM Start the FastAPI server
echo ============================================================
echo  Starting FastAPI Server
echo ============================================================
echo.
echo  Service URL: http://localhost:8000
echo  Health Check: http://localhost:8000/
echo  OCR Health: http://localhost:8000/api/ocr/health
echo  Process Endpoint: http://localhost:8000/api/ocr/process
echo.
echo  Press Ctrl+C to stop the server
echo ============================================================
echo.

python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

pause
