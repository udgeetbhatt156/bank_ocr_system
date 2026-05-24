import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import ocr

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(
    title="Bank OCR Service",
    version="2.0.0",
    description="Advanced OCR service for bank statement processing with 99% accuracy"
)

# CORS middleware - allow frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register OCR router
app.include_router(ocr.router, prefix="/api/ocr", tags=["OCR"])

@app.get("/")
def health_check():
    return {
        "status": "running",
        "service": "Bank OCR Service",
        "version": "2.0.0",
        "features": [
            "Digital PDF extraction",
            "Scanned PDF OCR with preprocessing",
            "Multi-bank format support",
            "Automatic column mapping",
            "Wrapped row detection"
        ]
    }
