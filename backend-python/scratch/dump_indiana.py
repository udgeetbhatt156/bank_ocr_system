import pdfplumber
import os

pdf_path = r"C:\Users\udgee\bank_ocr_system\IndianaBank\Indiana Bank.pdf"
output_path = r"C:\Users\udgee\bank_ocr_system\IndianaBank\indiana_text.txt"

with pdfplumber.open(pdf_path) as pdf:
    with open(output_path, "w", encoding="utf-8") as f:
        for idx, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            f.write(f"--- PAGE {idx + 1} ---\n")
            f.write(text)
            f.write("\n\n")

print(f"Extracted text saved to {output_path}")

# Let's also print pages/tables structure check
with pdfplumber.open(pdf_path) as pdf:
    for idx, page in enumerate(pdf.pages):
        tables = page.extract_tables()
        print(f"Page {idx+1} has {len(tables)} tables")
        if tables:
            print(f"Table 0 shape: {len(tables[0])}x{len(tables[0][0])}")
