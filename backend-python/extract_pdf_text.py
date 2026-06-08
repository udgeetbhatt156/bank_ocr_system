"""Extract Wells Fargo pages 2-3 (the transaction pages)."""
import pdfplumber
import os

pdf_dir = 'combined-all-pdf'
f = 'Feb_2026_Botachic_Designs_llc.pdf'
with pdfplumber.open(os.path.join(pdf_dir, f)) as pdf:
    for i in [1, 2]:  # pages 2 and 3
        text = pdf.pages[i].extract_text() or ''
        print(f'\n--- PAGE {i+1} ({len(text)} chars) ---')
        print(text[:5000])
