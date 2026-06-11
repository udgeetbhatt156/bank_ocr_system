from app.services.digital_extractor import extract_digital_pdf
from pathlib import Path
import json

rows = extract_digital_pdf(Path(r'C:\Users\udgee\bank_ocr_system\OCR-PSB-Jan2AprMTD\01-2026 SNEADS TIRE AND OIL LLC.pdf'))
with open('debug_rows.json', 'w', encoding='utf-8') as f:
    json.dump(rows, f, indent=2)
