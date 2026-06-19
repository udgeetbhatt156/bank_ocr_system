import os
import logging
from typing import List, Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Header, Depends, status

from app.models.schemas import OCRResponse, StatementResult
from app.services.ocr_pipeline import process_uploaded_file

router = APIRouter()
LOGGER = logging.getLogger(__name__)

# Config
ALLOWED_DEVELOPER_EMAIL = os.getenv("PW_USER_EMAIL", "developer@example.com").strip()
ALLOWED_DEVELOPER_APP = os.getenv("PW_APPLICATION", "ocr_process_api").strip()
ALLOWED_PASSKEY = os.getenv("PW_PASSKEY", "").strip()

def verify_developer_headers(
    x_pw_application: str = Header(None, alias="X-PW-Application"),
    x_pw_useremail: str = Header(None, alias="X-PW-UserEmail"),
    x_pw_passkey: str = Header(None, alias="X-PW-PassKey")
):
    if not x_pw_application or not x_pw_useremail:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized. Missing required headers: X-PW-Application, X-PW-UserEmail"
        )
    
    if x_pw_useremail.lower() != ALLOWED_DEVELOPER_EMAIL.lower():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized. This endpoint is restricted to a specific developer email."
        )
    
    if x_pw_application != ALLOWED_DEVELOPER_APP:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized. Invalid Application Name provided."
        )
    
    if ALLOWED_PASSKEY and x_pw_passkey != ALLOWED_PASSKEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized. Invalid PassKey provided."
        )
    return True

@router.post("/ocr/process", response_model=OCRResponse, dependencies=[Depends(verify_developer_headers)])
async def developer_process_documents(
    files: List[UploadFile] = File(...),
    bank_hint: Optional[str] = Form(None),
):
    """
    Developer API: Process bank statement documents WITH duplicate detection hashes.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    results: List[StatementResult] = []
    for upload in files:
        results.append(
            await process_uploaded_file(
                upload, with_duplicate_check=True, bank_hint=bank_hint,
            )
        )

    return OCRResponse(status="success", documents=results)
