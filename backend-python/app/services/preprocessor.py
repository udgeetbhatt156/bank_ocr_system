"""
Image Preprocessing Service for Scanned PDFs
Handles deskewing, denoising, CLAHE, and Sauvola binarization
"""
import cv2
import numpy as np
from pathlib import Path
from typing import List
from pdf2image import convert_from_path
from skimage.filters import threshold_sauvola


def deskew_image(image: np.ndarray) -> np.ndarray:
    """Deskew image using minAreaRect angle detection"""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) == 0:
        return image
    
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    
    # Only deskew if angle is significant
    if abs(angle) < 0.5:
        return image
    
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return rotated


def denoise_image(image: np.ndarray) -> np.ndarray:
    """Apply fastNlMeansDenoising to remove noise"""
    if len(image.shape) == 3:
        return cv2.fastNlMeansDenoisingColored(image, None, 10, 10, 7, 21)
    else:
        return cv2.fastNlMeansDenoising(image, None, 10, 7, 21)


def apply_clahe(image: np.ndarray) -> np.ndarray:
    """Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)"""
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def apply_sauvola_threshold(image: np.ndarray, window_size: int = 25) -> np.ndarray:
    """
    Apply Sauvola binarization - better for faded/uneven lighting
    
    Args:
        image: Grayscale image
        window_size: Local window size for threshold calculation
        
    Returns:
        Binary image
    """
    if len(image.shape) == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    thresh_sauvola = threshold_sauvola(image, window_size=window_size)
    binary = (image > thresh_sauvola).astype(np.uint8) * 255
    return binary


def preprocess_scanned_pdf(file_path: Path, dpi: int = 300) -> List[np.ndarray]:
    """
    previos dpi was 300
    Complete preprocessing pipeline for scanned PDFs
    
    Args:
        file_path: Path to PDF file
        dpi: Resolution for PDF to image conversion (300 recommended)
        
    Returns:
        List of preprocessed images (one per page)
    """
    # Convert PDF to images at 300 DPI (critical for accuracy)
    images = convert_from_path(str(file_path), dpi=dpi)
    
    processed_images = []
    for pil_image in images:
        # Convert PIL to OpenCV format
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        
        # Step 1: Deskew. PaddleOCR performs best on the natural page image;
        # aggressive denoise/threshold filters can collapse table geometry.
        img = deskew_image(img)

        processed_images.append(img)
    
    return processed_images
