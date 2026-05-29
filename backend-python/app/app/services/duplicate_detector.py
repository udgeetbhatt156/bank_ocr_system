"""
Duplicate Detector Service
Detects duplicate bank statements using multiple strategies
"""
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

from app.models.schemas import Transaction, StatementResult
from app.services.hash_service import (
    generate_file_hash,
    generate_content_hash,
    generate_transaction_fingerprint,
    calculate_content_similarity
)

LOGGER = logging.getLogger(__name__)

# Similarity threshold for considering statements as duplicates
SIMILARITY_THRESHOLD = 0.95  # 95% similarity


class DuplicateCheckResult:
    """Result of duplicate detection check"""
    
    def __init__(
        self,
        is_duplicate: bool,
        duplicate_type: Optional[str] = None,
        confidence: float = 0.0,
        original_filename: Optional[str] = None,
        message: Optional[str] = None,
        file_hash: Optional[str] = None,
        content_hash: Optional[str] = None,
        fingerprint: Optional[str] = None
    ):
        self.is_duplicate = is_duplicate
        self.duplicate_type = duplicate_type  # "exact_file", "exact_content", "similar_content"
        self.confidence = confidence
        self.original_filename = original_filename
        self.message = message
        self.file_hash = file_hash
        self.content_hash = content_hash
        self.fingerprint = fingerprint
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_duplicate": self.is_duplicate,
            "duplicate_type": self.duplicate_type,
            "confidence": self.confidence,
            "original_filename": self.original_filename,
            "message": self.message,
            "file_hash": self.file_hash,
            "content_hash": self.content_hash,
            "fingerprint": self.fingerprint
        }


def check_for_duplicates(
    file_path: Path,
    transactions: List[Transaction],
    metadata: Dict[str, Any],
    existing_statements: Optional[List[Dict[str, Any]]] = None
) -> DuplicateCheckResult:
    """
    Comprehensive duplicate detection using multiple strategies.
    
    Strategy 1: Exact file match (same binary content)
    Strategy 2: Exact content match (same extracted data)
    Strategy 3: Similar content match (fuzzy matching for near-duplicates)
    
    Args:
        file_path: Path to the uploaded PDF file
        transactions: Extracted transactions from the file
        metadata: Statement metadata (bank name, account number, etc.)
        existing_statements: List of previously processed statements with their hashes
        
    Returns:
        DuplicateCheckResult with detection details
    """
    LOGGER.info(f"Checking for duplicates: {file_path.name}")
    
    # Generate hashes for the current file
    try:
        file_hash = generate_file_hash(file_path)
        content_hash = generate_content_hash(transactions, metadata)
        fingerprint = generate_transaction_fingerprint(transactions)
    except Exception as e:
        LOGGER.error(f"Failed to generate hashes: {e}")
        return DuplicateCheckResult(
            is_duplicate=False,
            message=f"Hash generation failed: {e}",
            file_hash=None,
            content_hash=None,
            fingerprint=None
        )
    
    # If no existing statements provided, return hashes only
    if not existing_statements:
        LOGGER.info("No existing statements to compare against")
        return DuplicateCheckResult(
            is_duplicate=False,
            file_hash=file_hash,
            content_hash=content_hash,
            fingerprint=fingerprint
        )
    
    # Strategy 1: Check for exact file match
    for stmt in existing_statements:
        if stmt.get("file_hash") == file_hash:
            LOGGER.warning(f"Exact file duplicate detected: {file_path.name} matches {stmt.get('filename')}")
            return DuplicateCheckResult(
                is_duplicate=True,
                duplicate_type="exact_file",
                confidence=1.0,
                original_filename=stmt.get("filename"),
                message=f"This file is an exact duplicate of '{stmt.get('filename')}' uploaded previously.",
                file_hash=file_hash,
                content_hash=content_hash,
                fingerprint=fingerprint
            )
    
    # Strategy 2: Check for exact content match
    for stmt in existing_statements:
        if stmt.get("content_hash") == content_hash:
            LOGGER.warning(f"Exact content duplicate detected: {file_path.name} matches {stmt.get('filename')}")
            return DuplicateCheckResult(
                is_duplicate=True,
                duplicate_type="exact_content",
                confidence=1.0,
                original_filename=stmt.get("filename"),
                message=f"This statement contains identical transaction data to '{stmt.get('filename')}' (possibly rescanned or renamed).",
                file_hash=file_hash,
                content_hash=content_hash,
                fingerprint=fingerprint
            )
    
    # Strategy 3: Check for similar content (fuzzy matching)
    for stmt in existing_statements:
        # Only compare if fingerprints match (quick pre-filter)
        if stmt.get("fingerprint") == fingerprint:
            LOGGER.warning(f"Similar content detected: {file_path.name} matches {stmt.get('filename')}")
            return DuplicateCheckResult(
                is_duplicate=True,
                duplicate_type="similar_content",
                confidence=0.95,
                original_filename=stmt.get("filename"),
                message=f"This statement appears very similar to '{stmt.get('filename')}' (same transactions with minor variations).",
                file_hash=file_hash,
                content_hash=content_hash,
                fingerprint=fingerprint
            )
    
    # No duplicates found
    LOGGER.info(f"No duplicates found for {file_path.name}")
    return DuplicateCheckResult(
        is_duplicate=False,
        message="No duplicates detected",
        file_hash=file_hash,
        content_hash=content_hash,
        fingerprint=fingerprint
    )


def compare_statements(
    statement1: StatementResult,
    statement2: StatementResult
) -> float:
    """
    Compare two processed statements and return similarity score.
    
    Args:
        statement1: First statement result
        statement2: Second statement result
        
    Returns:
        Similarity score (0.0 to 1.0)
    """
    # Check metadata similarity
    metadata_matches = 0
    metadata_total = 0
    
    if statement1.bank_name and statement2.bank_name:
        metadata_total += 1
        if statement1.bank_name.lower() == statement2.bank_name.lower():
            metadata_matches += 1
    
    if statement1.account_number and statement2.account_number:
        metadata_total += 1
        # Normalize account numbers for comparison
        acc1 = statement1.account_number.replace("*", "").replace("X", "")
        acc2 = statement2.account_number.replace("*", "").replace("X", "")
        if acc1 and acc2 and acc1 == acc2:
            metadata_matches += 1
    
    if statement1.current_balance and statement2.current_balance:
        metadata_total += 1
        if abs(float(statement1.current_balance) - float(statement2.current_balance)) < 0.01:
            metadata_matches += 1
    
    metadata_similarity = metadata_matches / metadata_total if metadata_total > 0 else 0.5
    
    # Check transaction similarity
    transaction_similarity = calculate_content_similarity(
        statement1.transactions,
        statement2.transactions
    )
    
    # Combined score (weighted average)
    overall_similarity = (transaction_similarity * 0.8) + (metadata_similarity * 0.2)
    
    LOGGER.info(
        f"Statement comparison: {statement1.filename} vs {statement2.filename} = "
        f"{overall_similarity:.2%} (txn: {transaction_similarity:.2%}, meta: {metadata_similarity:.2%})"
    )
    
    return overall_similarity


def is_duplicate_statement(
    statement: StatementResult,
    existing_statements: List[StatementResult],
    threshold: float = SIMILARITY_THRESHOLD
) -> Optional[StatementResult]:
    """
    Check if a statement is a duplicate of any existing statement.
    
    Args:
        statement: Statement to check
        existing_statements: List of existing statements
        threshold: Similarity threshold (default 0.95)
        
    Returns:
        The original statement if duplicate found, None otherwise
    """
    for existing in existing_statements:
        similarity = compare_statements(statement, existing)
        if similarity >= threshold:
            LOGGER.warning(
                f"Duplicate detected: {statement.filename} is {similarity:.2%} similar to {existing.filename}"
            )
            return existing
    
    return None


def generate_duplicate_report(
    duplicate_result: DuplicateCheckResult
) -> Dict[str, Any]:
    """
    Generate a detailed report about duplicate detection.
    
    Args:
        duplicate_result: Result from duplicate detection
        
    Returns:
        Dictionary with detailed report
    """
    report = {
        "is_duplicate": duplicate_result.is_duplicate,
        "severity": "high" if duplicate_result.confidence >= 0.95 else "medium",
        "details": duplicate_result.to_dict(),
        "recommendation": _get_recommendation(duplicate_result),
        "actions": _get_suggested_actions(duplicate_result)
    }
    
    return report


def _get_recommendation(result: DuplicateCheckResult) -> str:
    """Get recommendation based on duplicate detection result"""
    if not result.is_duplicate:
        return "This statement appears to be unique. Safe to process."
    
    if result.duplicate_type == "exact_file":
        return "This is an exact copy of a previously uploaded file. Processing it will create duplicate transactions."
    
    if result.duplicate_type == "exact_content":
        return "This statement contains identical transaction data to a previous upload. It may be a rescanned or renamed version of the same statement."
    
    if result.duplicate_type == "similar_content":
        return "This statement is very similar to a previous upload. Review carefully before processing."
    
    return "Duplicate detected. Review before processing."


def _get_suggested_actions(result: DuplicateCheckResult) -> List[str]:
    """Get suggested actions based on duplicate detection result"""
    if not result.is_duplicate:
        return ["Process normally"]
    
    actions = [
        "Skip this upload",
        f"View original statement: {result.original_filename}",
        "Compare side-by-side",
    ]
    
    if result.confidence < 1.0:
        actions.append("Force upload if you're certain this is different")
    
    return actions
