"""
Quick check script - Run this RIGHT AFTER uploading a PDF
The file will be in uploads/ folder briefly before being deleted
"""
import sys
import time
from pathlib import Path

uploads_dir = Path(__file__).parent / "uploads"

print("=" * 80)
print("Waiting for PDF upload...")
print("=" * 80)
print()
print("Instructions:")
print("1. Keep this script running")
print("2. Upload a PDF through the web interface")
print("3. This script will automatically analyze it")
print()
print("Watching uploads/ folder...")
print()

# Watch for new files
seen_files = set()
while True:
    current_files = set(uploads_dir.glob("*.pdf"))
    new_files = current_files - seen_files
    
    if new_files:
        for pdf_file in new_files:
            print(f"\n🎯 Found: {pdf_file.name}")
            print("-" * 80)
            
            # Quick analysis
            sys.path.insert(0, str(Path(__file__).parent))
            from app.services.ingestion import detect_pdf_type
            from app.services.ocr_engine import extract_digital_pdf
            from app.services.table_parser import detect_header_row, map_columns
            from app.services.postprocessor import parse_date
            
            try:
                # Detect type
                pdf_type = detect_pdf_type(pdf_file)
                print(f"PDF Type: {pdf_type}")
                
                if pdf_type == "digital":
                    # Extract
                    rows = extract_digital_pdf(pdf_file)
                    print(f"Rows extracted: {len(rows)}")
                    
                    # Show first few rows
                    print("\nFirst 5 rows:")
                    for i, row in enumerate(rows[:5], 1):
                        print(f"  {i}. {row}")
                    
                    # Detect header
                    header_idx = detect_header_row(rows)
                    if header_idx is not None:
                        print(f"\nHeader row: {header_idx}")
                        print(f"Header: {rows[header_idx]}")
                        
                        # Map columns
                        col_map = map_columns(rows[header_idx])
                        print(f"\nColumn mapping: {col_map}")
                        
                        # Check dates
                        if 'date' in col_map:
                            data_rows = rows[header_idx + 1:]
                            date_col = col_map['date']
                            
                            print(f"\nChecking dates in first 5 data rows:")
                            dates_found = 0
                            for i, row in enumerate(data_rows[:5], 1):
                                if date_col < len(row):
                                    raw_date = row[date_col]
                                    parsed_date = parse_date(raw_date)
                                    if parsed_date:
                                        dates_found += 1
                                        print(f"  ✓ Row {i}: '{raw_date}' → {parsed_date}")
                                    else:
                                        print(f"  ✗ Row {i}: '{raw_date}' → NOT RECOGNIZED")
                            
                            if dates_found == 0:
                                print("\n⚠️  NO DATES FOUND!")
                                print("This is why you're getting 0 transactions.")
                                print("\nDate format in your PDF is not recognized.")
                                print("You need to add this date format to the parser.")
                            else:
                                print(f"\n✓ Found {dates_found} valid dates")
                        else:
                            print("\n⚠️  NO DATE COLUMN FOUND!")
                            print("This is why you're getting 0 transactions.")
                    else:
                        print("\n⚠️  NO HEADER ROW FOUND!")
                        print("Showing all rows:")
                        for i, row in enumerate(rows[:10], 1):
                            print(f"  {i}. {row}")
                else:
                    print("PDF is scanned - requires OCR processing")
                    print("Make sure Poppler is installed.")
                    
            except Exception as e:
                print(f"\n❌ Error: {e}")
                import traceback
                traceback.print_exc()
            
            print("\n" + "=" * 80)
            print("Analysis complete!")
            print("=" * 80)
            
        seen_files = current_files
    
    time.sleep(0.5)
