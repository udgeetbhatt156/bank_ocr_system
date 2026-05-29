"""
Image Preprocessing Service for Scanned PDFs
Handles deskewing, adaptive contrast enhancement, denoising, and
border removal for optimal OCR accuracy.
"""
import cv2
import numpy as np
from pathlib import Path
from typing import List
from pdf2image import convert_from_path
from skimage.filters import threshold_sauvola


def deskew_image(image: np.ndarray) -> np.ndarray:
    """Deskew image using minAreaRect angle detection."""
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
    rotated = cv2.warpAffine(
        image, M, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return rotated


def remove_borders(image: np.ndarray, border_pct: float = 0.01) -> np.ndarray:
    """
    Remove black borders from scanned pages.

    Many scanners add a thin black border or shadow. This crops it off
    using a percentage of the image dimensions.
    """
    h, w = image.shape[:2]
    top = int(h * border_pct)
    bottom = h - int(h * border_pct)
    left = int(w * border_pct)
    right = w - int(w * border_pct)
    if top < bottom and left < right:
        return image[top:bottom, left:right]
    return image


def assess_image_quality(image: np.ndarray) -> dict:
    """
    Assess image quality metrics to decide which preprocessing steps are needed.

    Returns dict with:
      - contrast_ratio: 0..1 (higher = better contrast)
      - noise_level: 0..1 (higher = noisier)
      - brightness: mean pixel value 0..255
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image

    # Contrast: ratio of std to mean
    mean_val = float(np.mean(gray))
    std_val = float(np.std(gray))
    contrast_ratio = min(1.0, std_val / max(mean_val, 1.0))

    # Noise: estimate using Laplacian variance
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    # Normalize: typical document range is 100-2000
    noise_level = min(1.0, laplacian_var / 2000.0)

    return {
        "contrast_ratio": contrast_ratio,
        "noise_level": noise_level,
        "brightness": mean_val,
    }


def denoise_image(image: np.ndarray) -> np.ndarray:
    """
    Apply bilateral filter for denoising.

    Bilateral filtering preserves edges better than fastNlMeansDenoising,
    which is critical for preserving thin text strokes in bank statements.
    """
    if len(image.shape) == 3:
        return cv2.bilateralFilter(image, d=9, sigmaColor=75, sigmaSpace=75)
    else:
        return cv2.bilateralFilter(image, d=9, sigmaColor=75, sigmaSpace=75)


def apply_clahe(image: np.ndarray) -> np.ndarray:
    """Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)."""
    if len(image.shape) == 3:
        # Apply CLAHE to the L channel of LAB color space
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l_channel = lab[:, :, 0]
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        lab[:, :, 0] = clahe.apply(l_channel)
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    else:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(image)


def apply_sauvola_threshold(image: np.ndarray, window_size: int = 25) -> np.ndarray:
    """
    Apply Sauvola binarization - better for faded/uneven lighting.

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


def remove_scan_artifacts(image: np.ndarray) -> np.ndarray:
    """
    Remove small noise dots and thin lines that are common in scanned documents.

    Uses morphological opening to remove tiny artifacts without affecting text.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image

    # Remove very small dots (noise from scanner)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    cleaned = cv2.morphologyEx(gray, cv2.MORPH_OPEN, kernel)

    if len(image.shape) == 3:
        # Apply the cleaning mask back to the color image
        mask = (gray != cleaned).astype(np.uint8) * 255
        result = image.copy()
        result[mask > 0] = [255, 255, 255]  # replace artifacts with white
        return result

    return cleaned


def preprocess_scanned_pdf(file_path: Path, dpi: int = 300) -> List[np.ndarray]:
    """
    Complete adaptive preprocessing pipeline for scanned PDFs.

    Args:
        file_path: Path to PDF file
        dpi: Resolution for PDF to image conversion (300 = industry standard)

    Returns:
        List of preprocessed images (one per page)
    """
    # Convert PDF to images at 300 DPI (critical for OCR accuracy)
    images = convert_from_path(str(file_path), dpi=dpi)

    processed_images = []
    for pil_image in images:
        # Convert PIL to OpenCV format
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

        # Step 1: Remove black borders from scan
        img = remove_borders(img)

        # Step 2: Deskew
        img = deskew_image(img)

        # Step 3: Assess image quality to decide further processing
        quality = assess_image_quality(img)

        # Step 4: Adaptive contrast enhancement
        # Only apply CLAHE if contrast is poor (faded documents)
        if quality["contrast_ratio"] < 0.25 or quality["brightness"] < 100:
            img = apply_clahe(img)

        # Step 5: Adaptive denoising
        # Only denoise if noise level is significant (noisy scans, fax copies)
        if quality["noise_level"] > 0.3:
            img = denoise_image(img)

        # Step 6: Remove scan artifacts (dots, specks)
        # Only for noisy images to avoid removing legitimate content
        if quality["noise_level"] > 0.5:
            img = remove_scan_artifacts(img)

        # Keep the color image for PaddleOCR 3.x which handles color well.
        # PaddleOCR's internal preprocessing is tuned for color input.
        processed_images.append(img)

    return processed_images
