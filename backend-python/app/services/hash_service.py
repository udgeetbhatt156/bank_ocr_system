"""
Hash Service - Generate unique hashes for duplicate detection
Implements content-based duplicate detection for bank statements
"""
import hashlib
import json
from pathlib import Path
from typing import List, Dict, Any
import logging

from app.models.schemas import Transaction

LOGGER = logging.getLogger(__name__)


def generate_file_hash(file_path: Path) -> str:
    """
    Generate SHA-256 hash of the entire file content.
    This detects exact file duplicates regardless of filename.
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        Hexadecimal SHA-256 hash string
    """
    sha256_hash = hashlib.sha256()
    
    try:
        with open(file_path, "rb") as f:
            # Read file in chunks to handle large files efficiently
            for byte_block in iter(lambda: f.read(65536), b""):
                sha256_hash.update(byte_block)
        
        file_hash = sha256_hash.hexdigest()
        LOGGER.info(f"Generated file hash for {file_path.name}: {file_hash[:16]}...")
        return file_hash
        
    except Exception as e:
        LOGGER.error(f"Failed to generate file hash for {file_path}: {e}")
        raise


def _safe_metadata_string(value: Any) -> str:
    """Normalize optional metadata values into safe strings."""
    if value is None:
        return ""
    return str(value).strip()


def generate_content_hash(
    transactions: List[Transaction],
    metadata: Dict[str, Any]
) -> str:
    """
    Generate hash based on extracted transaction content and metadata.
    This detects duplicate statements even if the PDF file is slightly different
    (e.g., different scan quality, minor formatting changes).
    
    Args:
        transactions: List of extracted transactions
        metadata: Statement metadata (bank name, account number, balance)
        
    Returns:
        Hexadecimal SHA-256 hash string
    """
    bank_name = _safe_metadata_string(metadata.get("bank_name")).lower()
    account_number = _normalize_account_number(_safe_metadata_string(metadata.get("account_number")))
    current_balance = metadata.get("current_balance")
    if current_balance in (None, ""):
        current_balance = None
    else:
        try:
            current_balance = float(current_balance)
        except (TypeError, ValueError):
            current_balance = None

    # Create a normalized representation of the statement content
    content_data = {
        "bank_name": bank_name,
        "account_number": account_number,
        "current_balance": current_balance,
        "transaction_count": len(transactions),
        "transactions": _normalize_transactions(transactions)
    }
    
    # Convert to deterministic JSON string
    content_json = json.dumps(content_data, sort_keys=True, default=str)
    
    # Generate hash
    content_hash = hashlib.sha256(content_json.encode('utf-8')).hexdigest()
    LOGGER.info(f"Generated content hash: {content_hash[:16]}... ({len(transactions)} transactions)")
    
    return content_hash


def _normalize_account_number(account_number: str) -> str:
    """
    Normalize account number by removing common variations.
    E.g., "****1234" and "XXXX1234" should be treated as same.
    """
    if not account_number:
        return ""
    
    # Remove spaces, dashes, and common masking characters
    normalized = account_number.replace(" ", "").replace("-", "")
    normalized = normalized.replace("*", "X").replace("x", "X")
    
    return normalized.strip().upper()


def _normalize_transactions(transactions: List[Transaction]) -> List[Dict[str, Any]]:
    """
    Create normalized representation of transactions for hashing.
    Focuses on key fields and rounds amounts to avoid floating point issues.
    """
    normalized = []
    
    for txn in transactions:
        normalized_txn = {
            "date": txn.date,
            "description": txn.description.strip().lower() if txn.description else "",
            "debit": round(float(txn.debit), 2) if txn.debit else None,
            "credit": round(float(txn.credit), 2) if txn.credit else None,
            "balance": round(float(txn.balance), 2) if txn.balance else None,
        }
        normalized.append(normalized_txn)
    
    # Sort by date and description for consistent ordering
    normalized.sort(key=lambda x: (x.get("date", ""), x.get("description", "")))
    
    return normalized


def _get_description_prefix(description: str, words: int = 3) -> str:
    """
    Extract first N words from description for fuzzy transaction matching.
    """
    if not description:
        return ""
    
    words_list = description.strip().lower().split()[:words]
    return " ".join(words_list)


def calculate_content_similarity(
    transactions1: List[Transaction],
    transactions2: List[Transaction]
) -> float:
    """
    Calculate similarity score between two sets of transactions.
    Returns a value between 0.0 (completely different) and 1.0 (identical).
    
    This is useful for detecting near-duplicates where OCR might have
    extracted slightly different data.
    
    Args:
        transactions1: First set of transactions
        transactions2: Second set of transactions
        
    Returns:
        Similarity score (0.0 to 1.0)
    """
    if not transactions1 and not transactions2:
        return 1.0
    
    if not transactions1 or not transactions2:
        return 0.0
    
    # If transaction counts are very different, likely not duplicates
    count_ratio = min(len(transactions1), len(transactions2)) / max(len(transactions1), len(transactions2))
    if count_ratio < 0.8:  # More than 20% difference in count
        return 0.0

    matching_transactions = 0
    
    for txn1 in transactions1:
        for txn2 in transactions2:
            if _transactions_match(txn1, txn2):
                matching_transactions += 1
                break
    
    similarity = matching_transactions / max(len(transactions1), len(transactions2))
    LOGGER.info(f"Calculated similarity: {similarity:.2%} ({matching_transactions}/{max(len(transactions1), len(transactions2))} matches)")
    
    return similarity


def _transactions_match(txn1: Transaction, txn2: Transaction, tolerance: float = 0.01) -> bool:
    """
    Check if two transactions are likely the same.
    
    Args:
        txn1: First transaction
        txn2: Second transaction
        tolerance: Amount tolerance for floating point comparison
        
    Returns:
        True if transactions match
    """
    # Date must match
    if txn1.date != txn2.date:
        return False
    
    # Amounts must match (within tolerance)
    debit1 = float(txn1.debit) if txn1.debit else 0.0
    debit2 = float(txn2.debit) if txn2.debit else 0.0
    credit1 = float(txn1.credit) if txn1.credit else 0.0
    credit2 = float(txn2.credit) if txn2.credit else 0.0
    
    if abs(debit1 - debit2) > tolerance or abs(credit1 - credit2) > tolerance:
        return False
    
    # Description should be similar (at least first 3 words match)
    desc1_prefix = _get_description_prefix(txn1.description, words=3)
    desc2_prefix = _get_description_prefix(txn2.description, words=3)
    
    if desc1_prefix != desc2_prefix:
        return False
    
    return True
