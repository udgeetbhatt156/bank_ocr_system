import cv2
import numpy as np
from pathlib import Path
from typing import List
from pdf2image import convert_from_path
from skimage.filters import threshold_sauvola


def deskew_image(image: np.ndarray) -> np.ndarray:
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
    h, w = image.shape[:2]
    top = int(h * border_pct)
    bottom = h - int(h * border_pct)
    left = int(w * border_pct)
    right = w - int(w * border_pct)
    if top < bottom and left < right:
        return image[top:bottom, left:right]
    return image


def assess_image_quality(image: np.ndarray) -> dict:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    mean_val = float(np.mean(gray))
    std_val = float(np.std(gray))
    contrast_ratio = min(1.0, std_val / max(mean_val, 1.0))
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    noise_level = min(1.0, laplacian_var / 2000.0)
    return {
        "contrast_ratio": contrast_ratio,
        "noise_level": noise_level,
        "brightness": mean_val,
    }


def denoise_image(image: np.ndarray) -> np.ndarray:
    if len(image.shape) == 3:
        return cv2.bilateralFilter(image, d=5, sigmaColor=50, sigmaSpace=50)
    return cv2.bilateralFilter(image, d=5, sigmaColor=50, sigmaSpace=50)


def apply_clahe(image: np.ndarray) -> np.ndarray:
    if len(image.shape) == 3:
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l_channel = lab[:, :, 0]
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        lab[:, :, 0] = clahe.apply(l_channel)
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(image)


def apply_sauvola_threshold(image: np.ndarray, window_size: int = 25) -> np.ndarray:
    if len(image.shape) == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    thresh_sauvola = threshold_sauvola(image, window_size=window_size)
    binary = (image > thresh_sauvola).astype(np.uint8) * 255
    return binary


def remove_scan_artifacts(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    cleaned = cv2.morphologyEx(gray, cv2.MORPH_OPEN, kernel)
    if len(image.shape) == 3:
        mask = (gray != cleaned).astype(np.uint8) * 255
        result = image.copy()
        result[mask > 0] = [255, 255, 255]
        return result
    return cleaned


def preprocess_scanned_pdf(file_path: Path, dpi: int = 200) -> List[np.ndarray]:
    images = convert_from_path(str(file_path), dpi=dpi)
    processed_images = []
    for pil_image in images:
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        img = remove_borders(img)
        quality = assess_image_quality(img)
        if quality["contrast_ratio"] < 0.3 or quality["noise_level"] > 0.4:
            img = deskew_image(img)
        if quality["contrast_ratio"] < 0.25 or quality["brightness"] < 100:
            img = apply_clahe(img)
        if quality["noise_level"] > 0.4:
            img = denoise_image(img)
        if quality["noise_level"] > 0.6:
            img = remove_scan_artifacts(img)
        processed_images.append(img)
    return processed_images
