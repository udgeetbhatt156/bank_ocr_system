# BankOCR Parser Template — First Service Credit Union (FSCU)
# Template ID: FSCU_SMALL_BIZ_CHECKING_V1
# Statement Type: Small Business Checking / Business Savings
# Issuer: First Service Credit Union (Houston, TX)
# Statement Format: Hybrid PDF — scanned image body + sparse text layer
# OCR Strategy: RASTERIZE → OCR (pytesseract / PaddleOCR) — pdfplumber text layer is UNRELIABLE

---

## 1. DOCUMENT FINGERPRINT (Detection Keys)

Use ALL of the following signals to confidently identify this template:

| Signal | Value |
|---|---|
| Institution Name | `First Service Credit Union` OR `First Service` + `Credit Union` |
| Header Title | `Statement of Account` (top-right of every page) |
| Issuer Address | `P.O. Box 941914, Houston, TX 77094-8914` |
| Phone | `713-676-7777` / `800-678-5197` |
| Website | `FSCU.com` |
| Section Header | `Small Business Checking (XXXX)` and/or `Business Savings (XXXX)` |
| Column Headers | `Eff. Date | Deposit | Withdrawal | Balance | Description` |
| Account Summary Label | `ACCOUNT SUMMARY` block on page 1 |
| Recap Block | `Cleared Draft Recap` on final transaction page |
| Logo Watermarks | Repeating `TFC` diagonal watermarks across all pages |
| Footer Logos | `EQUAL HOUSING OPPORTUNITY` + `NCUA` on page 1 |
| PDF Nature | Sparse text layer — MUST use OCR on rasterized images |

**Minimum match to trigger this template: 3+ signals above.**

---

## 2. PDF CHARACTERISTICS & RENDERING STRATEGY

```
PDF Type         : Hybrid (scanned image + sparse text overlay)
Page Count       : 4 statement pages + 1 notice page (5 total for this sample)
Page Size        : 612 × 792 pts (US Letter)
Text Layer       : UNRELIABLE — only watermark trace numbers appear in text layer
                   (e.g., 515321100121, 515426218948...) — these are reference codes
                   embedded at rotated angles in the background, NOT transaction data
DPI for OCR      : Use 150–200 DPI (pdftoppm -r 150 -png)
OCR Engine       : pytesseract PSM 6 (uniform block) OR PaddleOCR PP-StructureV3
Pre-processing   : No deskew needed; contrast enhancement may improve accuracy
                   on faded/watermarked areas
Page 4           : Disclosures/legal text only — skip for transactions
Page 5           : Fund availability notice insert — skip for transactions
```

**Critical Note:** Do NOT rely on `pdfplumber.extract_text()` for transaction data. The main body of each page is a rasterized image. The text layer only contains the column headers and a few watermark reference codes. Always rasterize → OCR.

---

## 3. METADATA EXTRACTION

### 3.1 Header Metadata (Page 1, top-right box)
Extract from the 3-cell table at top-right of page 1:

```
Field            : Account Number
Location         : Header box, cell 1
Example Value    : 5689715
Regex            : r'(\d{7})\s+\d{2}/\d{2}/\d{2}'   # 7-digit account number

Field            : Statement Period
Location         : Header box, cell 2
Example Value    : 06/01/25 - 06/30/25
Regex            : r'(\d{2}/\d{2}/\d{2})\s*[-–]\s*(\d{2}/\d{2}/\d{2})'

Field            : Page
Location         : Header box, cell 3
Example Value    : 1 of 4
Regex            : r'(\d+)\s+of\s+(\d+)'
```

### 3.2 Customer / Business Information (Page 1, address block)
```
Field            : Customer / Business Name (Line 1)
Location         : Left-center address block, page 1
Example Value    : Walker's Total Solutions LLC
Extraction       : First non-empty line after logo area, before ACCOUNT SUMMARY

Field            : Street Address
Example Value    : 23994 Gay Lake

Field            : City / State / ZIP
Example Value    : Montgomery TX 77356
```

### 3.3 Bank Name
```
Static Value     : First Service Credit Union
```

### 3.4 Account Summary Block (Page 1)
```
Shares Section:
  Savings           : $5.00
  Money Market      : $0.00
  Christmas Club    : $0.00
  Checking          : $2,285.79
  CD                : $0.00
  IRA               : $0.00
  Total Deposits    : $2,290.79

Loans Section:
  Line of Credit    : $0.00
  Auto              : $0.00
  Personal          : $0.00
  Holiday Loan      : $0.00
  Home Equity       : $0.00
  Total Loans       : $0.00
```

---

## 4. ACCOUNT SECTION DETECTION

This statement contains TWO sub-accounts. Detect each by its bold dark-background section header:

### Section A: Business Savings
```
Trigger Text     : "Business Savings (XXXX)"
Account Suffix   : 4-digit number in parentheses → e.g., (0004)
Summary Row      : BeginningBal | Debits/Withdrawals | Credits/Deposits | EndingBal | YTD Dividends
Example Values   : $5.00 | $0.00 | $0.00 | $5.00 | $0.00
Special Case     : "No Transactions This Period" → empty transaction list
Ending Balance   : $5.00
```

### Section B: Small Business Checking
```
Trigger Text     : "Small Business Checking (XXXX)"
Account Suffix   : e.g., (0075)
Summary Row      : BeginningBal | Debits/Withdrawals | Credits/Deposits | EndingBal | YTD Dividends
Example Values   : $78,854.89 | $95,933.09 | $19,363.99 | $2,285.79 | $0.00
Ending Balance   : $2,285.79   ← THIS IS THE CURRENT/ENDING BALANCE
Authorized Signer: Todrick J Walker
```

**The CURRENT BALANCE to report = Small Business Checking Ending Balance = $2,285.79**

---

## 5. TRANSACTION TABLE STRUCTURE

### 5.1 Column Layout (approximate pixel X-anchors at 150 DPI / 612pt page)
```
Column       | PDF X (pts) | Label
-------------|-------------|----------------------------
Eff. Date    | 25–90       | Transaction effective date
Deposit      | 90–140      | Credit amount (positive)
Withdrawal   | 141–200     | Debit amount (negative, shown with minus sign)
Balance      | 200–253     | Running balance after transaction
Description  | 254–590     | Full transaction description text
```

**Critical:** Deposit and Withdrawal are SEPARATE columns. A row will have either a Deposit OR a Withdrawal, never both (except the beginning/ending balance rows which have neither). Do NOT merge them into a single signed amount without preserving the original column.

### 5.2 Column Parsing Rules

**Eff. Date:**
- Format: MM/DD/YY (e.g., `06/02/25`)
- Always the leftmost column
- Multiple rows can share the same date (same-day transactions)
- Beginning Balance row: date = statement start date
- Ending Balance row: date = statement end date

**Deposit (Credit):**
- Positive numeric value, no sign
- Example: `798.44`, `2,042.30`, `449.78`, `8,570.00`
- OCR may sometimes read the `$` sign — strip it

**Withdrawal (Debit):**
- Shown with leading minus sign in source: `-605.42`, `-6,500.00`
- OCR may misread the minus as a backtick, dash, or quote character — normalize all to `-`
- May also appear as `"126.92` or `'126.92` — these are misread minus signs
- Example corrections: `"605.42` → `-605.42`, `'93.30` → `-93.30`

**Balance:**
- Running balance after the transaction
- Large values with commas: `78,249.47`, `71,749.47`
- Dollar sign sometimes present — strip it
- Beginning Balance has `$` prefix (e.g., `$ 78,854.89`)

**Description:**
- Free-form text, can be long (50–100 characters)
- Contains transaction type + merchant/counterparty + location + reference codes
- Trailing trace codes (e.g., `515321100121`) are part of the description
- Multi-word, must capture in full
- Common prefixes: `ACH Withdrawal`, `ACH Deposit`, `Draft Withdrawal`, `Card purchase`,
  `Check Deposit`, `Fee Withdrawal`, `Deposit INCOMING WIRE`

---

## 6. COMPLETE TRANSACTION LIST (Ground Truth for Template Training)

### Account: Business Savings (0004)
```
Date       | Deposit  | Withdrawal | Balance  | Description
-----------|----------|------------|----------|----------------------------------
06/01/25   |          |            | 5.00     | Beginning Balance
           |          |            |          | No Transactions This Period
06/30/25   |          |            | 5.00     | Ending Balance
```

### Account: Small Business Checking (0075) — Pages 1–3

```
Date       | Deposit    | Withdrawal  | Balance    | Description
-----------|------------|-------------|------------|--------------------------------------------------
06/01/25   |            |             | 78,854.89  | Beginning Balance
06/02/25   |            | -605.42     | 78,249.47  | ACH Withdrawal Nav Technologies, NAVPC PYMT, Todrick Walker Nav Technologie
06/02/25   |            | -6,500.00   | 71,749.47  | Draft Withdrawal Draft # 128 Tracer 127000001006042
06/02/25   |            | -39.00      | 71,710.47  | Bill Payment Card purchase DUDA WEBSITES DUDA.CO, CO, HO593R2P 515321100121
06/03/25   |            | -1,208.05   | 70,502.42  | ACH Withdrawal Nav Technologies, NAVPC PYMT, Todrick Walker Nav Technologie
06/03/25   |            | -93.30      | 70,409.12  | Card purchase BABIN'S WOODLANDS SHENAHDOAH, TX, VBASE2 515426218948
06/03/25   |            | -12,485.00  | 57,924.12  | Draft Withdrawal Draft # 129 Tracer 127000001008150
06/04/25   | 798.44     |             | 58,722.56  | ACH Deposit INTUIT 37250003, DEPOSIT, WALKERS TOTAL SOLUTION
06/04/25   |            | -4,431.70   | 54,290.86  | ACH Withdrawal MARKETING REFRES, SALE, WALKERS TOTAL SOLUTION
06/04/25   |            | -7.98       | 54,282.88  | ACH Withdrawal INTUIT 51349153, TRAN FEE, WALKERS TOTAL SOLUTION
06/04/25   |            | -54.80      | 54,228.08  | Card purchase SHELL OIL13126489015 SPRING, TX, VBASE2 515520361321
06/04/25   |            | -53.29      | 54,174.79  | Card purchase NAV TECH 855-226-8388 NAV.COM, UT, CH2HCONV 515524100108
06/04/25   |            | -953.10     | 53,221.69  | Draft Withdrawal Draft # 146 Tracer 127000004006058
06/04/25   |            | -95.48      | 53,126.21  | Card purchase OLIVE GARDEN 0024477 HOUSTON, TX, 00000046 515525219753
06/05/25   |            | -260.69     | 52,865.52  | ACH Withdrawal Nav Technologies, NAVPC PYMT, Todrick Walker Nav Technologie
06/05/25   | 449.78     |             | 53,315.30  | Check Deposit
06/05/25   |            | -50.00      | 53,265.30  | Card purchase BRIGHT FOOD MART SPRING, TX, VBASE2 515628100287
06/06/25   |            | -126.92     | 53,138.38  | ACH Withdrawal Texas SDU, CHILDSUPP, Walkers Total Solution
06/06/25   |            | -55.82      | 53,082.56  | ACH Withdrawal Nav Technologies, NAVPC PYMT, Todrick Walker Nav Technologie
06/06/25   |            | -3,115.38   | 49,967.18  | ACH Withdrawal PAYROLL, PAYROLL, WALKERS TOTAL SOLUTION
06/06/25   |            | -2,861.54   | 47,105.64  | ACH Withdrawal PAYROLL, PAYROLL, WALKERS TOTAL SOLUTION
06/06/25   |            | -1,072.07   | 46,033.57  | ACH Withdrawal INTUIT 61599312, PAYROLL, WALKERS TOTAL SOLUTION
06/06/25   |            | -780.06     | 45,253.51  | ACH Withdrawal INTUIT 61599312, PAYROLL, WALKERS TOTAL SOLUTION
06/06/25   |            | -1,168.85   | 44,084.66  | ACH Withdrawal INTUIT 61599312, PAYROLL, WALKERS TOTAL SOLUTION
06/06/25   |            | -1,700.52   | 42,384.14  | ACH Withdrawal INTUIT 61599312, PAYROLL, WALKERS TOTAL SOLUTION
06/06/25   |            | -923.50     | 41,460.64  | ACH Withdrawal INTUIT 61599312, PAYROLL, WALKERS TOTAL SOLUTION
06/06/25   |            | -396.31     | 41,064.33  | ACH Withdrawal INTUIT 61599312, PAYROLL, WALKERS TOTAL SOLUTION
06/06/25   |            | -500.26     | 40,564.07  | ACH Withdrawal INTUIT 61599312, PAYROLL, WALKERS TOTAL SOLUTION
06/06/25   |            | -159.00     | 40,405.07  | ACH Withdrawal INTUIT 61599312, PAYROLL, WALKERS TOTAL SOLUTION
06/06/25   |            | -1,737.43   | 38,667.64  | ACH Withdrawal INTUIT 96882955, TAX, WALKERS TOTAL SOLUTION
06/06/25   |            | -97.39      | 38,570.25  | Card purchase CHEDDAR'S 0202043 SPRING, TX, 00007282 515720221107
06/06/25   |            | -311.27     | 38,258.98  | Card purchase INTUIT *QBooks Payroll CL.INTUIT.COM, CA, VBASE2 515728101623
06/06/25   |            | -693.16     | 37,565.82  | Card purchase AIRBNB * HMP8K25WCE AIRBNB.COM, CA, VBASE2 515725714748
06/06/25   |            | -50.00      | 37,515.82  | Card purchase SAN ANTONIO RENTALS FELIZSTAYS.CO, TX, LO1NGOQC 515821100003
06/07/25   |            | -5.00       | 37,510.82  | Fee Withdrawal Statement Fee
06/09/25   | 2,042.30   |             | 39,553.12  | ACH Deposit INTUIT 70357333, DEPOSIT, WALKERS TOTAL SOLUTION
06/09/25   |            | -1,619.10   | 37,934.02  | ACH Withdrawal Nav Technologies, NAVPC PYMT, Todrick Walker Nav Technologie
06/09/25   |            | -61.06      | 37,872.96  | ACH Withdrawal INTUIT 84702893, TRAN FEE, WALKERS TOTAL SOLUTION
06/09/25   | 1,519.46   |             | 39,392.42  | Check Deposit
06/10/25   |            | -127.97     | 39,264.45  | ACH Withdrawal Nav Technologies, NAVPC PYMT, Todrick Walker Nav Technologie
06/10/25   |            | -500.00     | 38,764.45  | ACH Withdrawal PAYROLL, PAYROLL, WALKERS TOTAL SOLUTION
06/11/25   |            | -60.00      | 38,704.45  | Card purchase HWY 290 SWIFT HOCKLEY, TX, 001 516223368804
06/11/25   |            | -75.00      | 38,629.45  | Card purchase HWY 290 SWIFT HOCKLEY, TX, 001 516221368804
06/11/25   |            | -75.00      | 38,554.45  | Card purchase HWY 290 SWIFT HOCKLEY, TX, 001 516229368804
06/11/25   |            | -850.00     | 37,704.45  | Draft Withdrawal Draft # 192 Tracer 127000006005139
06/12/25   |            | -602.37     | 37,102.08  | ACH Withdrawal Nav Technologies, NAVPC PYMT, Todrick Walker Nav Technologie
06/12/25   |            | -10,230.00  | 26,872.08  | Draft Withdrawal Draft # 148 Tracer 127000006006406
06/12/25   |            | -10.00      | 26,862.08  | Card purchase COSA - CONVENTION CTR G 210-2078668, TX, VBASE2 516322222100
06/13/25   |            | -20.00      | 26,842.08  | Card purchase SQ *CASINO ST, INC SAN ANTONIO, TX, VBASE2 516428107249
06/13/25   |            | -2.60       | 26,839.48  | Card purchase DOLLARTREE SAN ANTONIO, TX, VBASE2 516420000721
06/13/25   |            | -126.92     | 26,712.56  | ACH Withdrawal Texas SDU, CHILDSUPP, Walkers Total Solution
06/13/25   |            | -136.44     | 26,576.12  | ACH Withdrawal Nav Technologies, NAVPC PYMT, Todrick Walker Nav Technologie
06/13/25   |            | -3,115.38   | 23,460.74  | ACH Withdrawal PAYROLL, PAYROLL, WALKERS TOTAL SOLUTION
06/13/25   |            | -2,861.54   | 20,599.20  | ACH Withdrawal PAYROLL, PAYROLL, WALKERS TOTAL SOLUTION
06/13/25   |            | -1,700.53   | 18,898.67  | ACH Withdrawal INTUIT 61878357, PAYROLL, WALKERS TOTAL SOLUTION
06/13/25   |            | -500.25     | 18,398.42  | ACH Withdrawal INTUIT 61878357, PAYROLL, WALKERS TOTAL SOLUTION
06/13/25   |            | -159.00     | 18,239.42  | ACH Withdrawal INTUIT 61878357, PAYROLL, WALKERS TOTAL SOLUTION
06/13/25   |            | -346.31     | 17,893.11  | ACH Withdrawal INTUIT 61878357, PAYROLL, WALKERS TOTAL SOLUTION
06/13/25   |            | -887.99     | 17,005.12  | ACH Withdrawal INTUIT 61878357, PAYROLL, WALKERS TOTAL SOLUTION
06/13/25   |            | -1,072.07   | 15,933.05  | ACH Withdrawal INTUIT 61878357, PAYROLL, WALKERS TOTAL SOLUTION
06/13/25   |            | -923.50     | 15,009.55  | ACH Withdrawal INTUIT 61878357, PAYROLL, WALKERS TOTAL SOLUTION
06/13/25   |            | -758.36     | 14,251.19  | ACH Withdrawal INTUIT 61878357, PAYROLL, WALKERS TOTAL SOLUTION
06/13/25   |            | -507.81     | 13,743.38  | ACH Withdrawal INTUIT 10170043, TAX, WALKERS TOTAL SOLUTION
06/13/25   |            | -190.20     | 13,553.18  | Card purchase YARD HOUSE ZK 0108362 SAN ANTONIO, TX, 08362042 516426225668
06/14/25   |            | -15.00      | 13,538.18  | Card purchase COSA - MARINA GARAGE 210-2078668, TX, VBASE2 516429222100
06/15/25   |            | -81.73      | 13,456.45  | Card purchase SMOKE BBQ - SKYLINE SAN ANTONIO, TX, 75720032 516626891206
06/15/25   |            | -68.00      | 13,388.45  | Card purchase BUC-EE'S #17 LULING, TX, VBASE2 516621109723
06/16/25   |            | -127.01     | 13,261.44  | Card purchase PY *SEAHOLIC SEAFOOD OY HOUSTON, TX, 34917117 516723500349
06/16/25   |            | -114.63     | 13,146.81  | Card purchase PY *SEAHOLIC SEAFOOD OY HOUSTON, TX, 34917125 516726500349
06/16/25   |            | -254.28     | 12,892.53  | ACH Withdrawal Nav Technologies, NAVPC PYMT, Todrick Walker Nav Technologie
06/17/25   |            | -327.61     | 12,564.92  | ACH Withdrawal Nav Technologies, NAVPC PYMT, Todrick Walker Nav Technologie
06/17/25   |            | -535.49     | 12,029.43  | ACH Withdrawal Nav Technologies, NAVPC PYMT, Todrick Walker Nav Technologie
06/17/25   |            | -2,500.00   | 9,529.43   | Draft Withdrawal Draft # 191 Tracer 127000005003673
06/18/25   |            | -182.89     | 9,346.54   | ACH Withdrawal Nav Technologies, NAVPC PYMT, Todrick Walker Nav Technologie
06/18/25   |            | -5,270.00   | 4,076.54   | Draft Withdrawal Draft # 193 Tracer 127000005005054
06/19/25   |            | -66.16      | 4,010.38   | Card purchase BOMBSHELLS (59) HOUSTON, TX, 00005286 517022378033
06/20/25   | 4,003.26   |             | 8,013.64   | ACH Deposit INTUIT 01924473, DEPOSIT, WALKERS TOTAL SOLUTION
06/20/25   |            | -126.92     | 7,886.72   | ACH Withdrawal Texas SDU, CHILDSUPP, Walkers Total Solution
06/20/25   |            | -431.12     | 7,455.60   | ACH Withdrawal Nav Technologies, NAVPC PYMT, Todrick Walker Nav Technologie
06/20/25   |            | -119.70     | 7,335.90   | ACH Withdrawal INTUIT 15521123, TRAN FEE, WALKERS TOTAL SOLUTION
06/20/25   |            | -500.00     | 6,835.90   | Draft Withdrawal Draft # 151
06/23/25   |            | -3,327.87   | 3,508.03   | Draft Withdrawal Draft # 147 Tracer 127000005005413
06/23/25   | 494.69     |             | 4,002.72   | ACH Deposit INTUIT 04294403, DEPOSIT, WALKERS TOTAL SOLUTION
06/23/25   |            | -175.97     | 3,826.75   | ACH Withdrawal Nav Technologies, NAVPC PYMT, Todrick Walker Nav Technologie
06/23/25   |            | -14.79      | 3,811.96   | ACH Withdrawal INTUIT 17857723, TRAN FEE, WALKERS TOTAL SOLUTION
06/23/25   | 1,486.06   |             | 5,298.02   | Check Deposit
06/23/25   |            | -700.00     | 4,598.02   | Draft Withdrawal Draft # 194 Tracer 127000005007544
06/23/25   |            | -450.00     | 4,148.02   | Draft Withdrawal Draft # 152 Tracer 127000005006906
06/23/25   |            | -375.00     | 3,773.02   | Draft Withdrawal Draft # 153 Tracer 127000005006976
06/23/25   |            | -380.00     | 3,393.02   | Draft Withdrawal Draft # 154 Tracer 127000005006333
06/24/25   |            | -643.24     | 2,749.78   | ACH Withdrawal Nav Technologies, NAVPC PYMT, Todrick Walker Nav Technologie
06/24/25   |            | -374.00     | 2,375.78   | Draft Withdrawal Draft # 155 Tracer 127000005008467
06/24/25   |            | -1,100.00   | 1,275.78   | Draft Withdrawal Draft # 196 Tracer 127000005008319
06/26/25   |            | -75.00      | 1,200.78   | Card purchase HWY 290 SWIFT HOCKLEY, TX, 001 517726385827
06/27/25   |            | -126.92     | 1,073.86   | ACH Withdrawal Texas SDU, CHILDSUPP, Walkers Total Solution
06/27/25   |            | -374.60     | 699.26     | ACH Withdrawal Nav Technologies, NAVPC PYMT, Todrick Walker Nav Technologie
06/27/25   |            | -175.00     | 524.26     | Card purchase SHELL OIL12983956017 JERSEY VILLAG, TX, VBASE2 517825387402
06/27/25   |            | -180.00     | 344.26     | Card purchase SHELL OIL 57543430904 ROSENBERG, TX, VBASE2 517822387414
06/27/25   |            | -27.05      | 317.21     | Card purchase SHELL OIL 57543430904 ROSENBERG, TX, VBASE2 517826387414
06/27/25   | 8,570.00   |             | 8,887.21   | Deposit INCOMING WIRE - THE LCF GROUP INC
06/28/25   |            | -100.00     | 8,787.21   | Card purchase SWIFT ELLA HOUSTON, TX, 001 517926388494
06/28/25   |            | -500.00     | 8,287.21   | Draft Withdrawal Draft # 200
06/28/25   |            | -1,300.00   | 6,987.21   | Draft Withdrawal Draft # 199
06/28/25   |            | -85.13      | 6,902.08   | Card purchase CHIMNEY ROCK FOOD MART HOUSTON, TX, VBASE2 517923108021
06/30/25   |            | -312.29     | 6,589.79   | ACH Withdrawal LCF 8884992939, LC06271010, Walker's Total S
06/30/25   |            | -374.00     | 6,215.79   | Draft Withdrawal Draft # 197 Tracer 127000002006045
06/30/25   |            | -2,300.00   | 3,915.79   | Draft Withdrawal Draft # 158 Tracer 127000002006140
06/30/25   |            | -450.00     | 3,465.79   | Draft Withdrawal Draft # 156 Tracer 127000002006224
06/30/25   |            | -380.00     | 3,085.79   | Draft Withdrawal Draft # 157 Tracer 127000002006259
06/30/25   |            | -800.00     | 2,285.79   | Draft Withdrawal Draft # 198 Tracer 127000002006312
06/30/25   |            |             | 2,285.79   | Ending Balance
```

**Total transactions (excl. Beginning/Ending): 91 rows**

---

## 7. CLEARED DRAFT RECAP (Page 3)

Parse this 4-column recap table separately. Each group has: Draft #, Date, Amount.
`*` after Draft # = out of sequence (flag in output).

```
Draft # | Date  | Amount    | Out of Seq?
--------|-------|-----------|------------
128     | 06/02 | 6,500.00  | No
129     | 06/03 | 12,485.00 | No
146     | 06/04 | 953.10    | Yes (146*)
147     | 06/23 | 3,327.87  | No
148     | 06/12 | 10,230.00 | No
151     | 06/20 | 500.00    | Yes (151*)
152     | 06/23 | 450.00    | No
153     | 06/23 | 375.00    | No
154     | 06/23 | 380.00    | No
155     | 06/24 | 374.00    | No
156     | 06/30 | 450.00    | No
157     | 06/30 | 380.00    | No
158     | 06/30 | 2,300.00  | No
191     | 06/17 | 2,500.00  | Yes (191*)
192     | 06/11 | 850.00    | No
193     | 06/18 | 5,270.00  | No
194     | 06/23 | 700.00    | No
196     | 06/24 | 1,100.00  | Yes (196*)
197     | 06/30 | 374.00    | No
198     | 06/30 | 800.00    | No
199     | 06/28 | 1,300.00  | No
200     | 06/28 | 500.00    | No
```

---

## 8. OCR CORRECTION RULES (FSCU-Specific)

### 8.1 Minus Sign Normalization
OCR frequently misreads the minus/negative sign in withdrawal amounts:
```python
MINUS_CORRECTIONS = {
    '"': '-',   # OCR reads " instead of -
    "'": '-',   # OCR reads ' instead of -
    '`': '-',   # OCR reads ` instead of -
    '~': '-',   # OCR reads ~ instead of -
    '—': '-',   # em dash misread
}

def normalize_withdrawal(raw: str) -> float:
    for bad, good in MINUS_CORRECTIONS.items():
        raw = raw.replace(bad, good, 1)
    raw = raw.replace(',', '').replace('$', '').strip()
    return float(raw)
```

### 8.2 Amount Parsing
```python
def parse_amount(raw: str) -> float | None:
    raw = raw.strip().replace(',', '').replace('$', '').replace(' ', '')
    if not raw or raw in ['-', '']:
        return None
    try:
        return float(raw)
    except ValueError:
        return None
```

### 8.3 Date Normalization
```python
import re
def parse_date(raw: str) -> str:
    # Input: "06/02/25" → Output: "2025-06-02"
    m = re.match(r'(\d{2})/(\d{2})/(\d{2})', raw.strip())
    if m:
        mo, d, y = m.groups()
        return f"20{y}-{mo}-{d}"
    return raw
```

### 8.4 Description Cleaning
- Strip leading `|` characters (OCR artifact from table borders)
- Strip trailing pipe characters
- Strip excess whitespace
- Preserve internal spaces, numbers, punctuation (merchant codes, tracer numbers)
- Do NOT strip trailing trace/reference numbers (e.g., `515321100121`) — they are part of the description

### 8.5 Common OCR Misreads in This Statement
```
OCR Reads           → Correct
-7,208.05           → -1,208.05   (1 misread as 7 — verify with balance math)
"4,437.70           → -4,431.70   (quote=minus; 7=1 in OCR)
3,508.03            → 3,508.03    ✓
575827700003        → 515821100003 (trace code; validate 12-digit pattern)
0 Statement         → "Statement"  (leading 0 artifact from logo OCR)
```

### 8.6 Balance Validation (CRITICAL)
After extracting each row, validate:
```python
def validate_balance(prev_balance, deposit, withdrawal, current_balance, tolerance=0.02):
    expected = prev_balance
    if deposit:
        expected += deposit
    if withdrawal:
        expected += withdrawal  # withdrawal is already negative
    return abs(expected - current_balance) <= tolerance
```
If balance doesn't reconcile, flag that row for manual review rather than silently accepting the OCR output.

---

## 9. PARSER PSEUDOCODE

```python
def parse_fscu_statement(pdf_path: str) -> dict:
    
    # Step 1: Rasterize
    images = rasterize_pdf(pdf_path, dpi=150)  # Returns list of PIL Images
    
    # Step 2: OCR all pages
    ocr_pages = [pytesseract.image_to_string(img, config='--psm 6') for img in images]
    
    # Step 3: Metadata from Page 1
    metadata = extract_metadata(ocr_pages[0])
    # → bank_name, account_number, statement_period, customer_name, customer_address
    
    # Step 4: Account Summary from Page 1
    summary = extract_account_summary(ocr_pages[0])
    # → total_deposits, total_loans, checking_balance, savings_balance
    
    # Step 5: Detect account sections
    sections = detect_sections(ocr_pages)
    # → [{"name": "Business Savings", "suffix": "0004", "pages": [0]},
    #    {"name": "Small Business Checking", "suffix": "0075", "pages": [0,1,2]}]
    
    # Step 6: Parse transactions per section
    for section in sections:
        section["summary"] = extract_section_summary(section)
        # → beginning_balance, total_debits, total_credits, ending_balance
        
        section["transactions"] = []
        for page_idx in section["pages"]:
            rows = extract_transaction_rows(ocr_pages[page_idx], page_idx)
            section["transactions"].extend(rows)
        
        # Step 7: Validate balances
        validate_transaction_chain(section["transactions"])
    
    # Step 8: Parse Cleared Draft Recap (last transaction page)
    draft_recap = extract_draft_recap(ocr_pages[2])
    
    # Step 9: Build output
    return {
        "bank_name": "First Service Credit Union",
        "account_number": metadata["account_number"],
        "statement_period": metadata["statement_period"],
        "customer_name": metadata["customer_name"],
        "customer_address": metadata["customer_address"],
        "current_balance": sections[1]["ending_balance"],  # Checking ending balance
        "accounts": sections,
        "draft_recap": draft_recap,
        "total_pages": len(images),
    }
```

---

## 10. EXPECTED OUTPUT SCHEMA

```json
{
  "bank_name": "First Service Credit Union",
  "account_number": "5689715",
  "statement_period": {
    "start": "2025-06-01",
    "end": "2025-06-30"
  },
  "customer_name": "Walker's Total Solutions LLC",
  "customer_address": {
    "street": "23994 Gay Lake",
    "city": "Montgomery",
    "state": "TX",
    "zip": "77356"
  },
  "current_balance": 2285.79,
  "authorized_signer": "Todrick J Walker",
  "accounts": [
    {
      "account_name": "Business Savings",
      "account_suffix": "0004",
      "beginning_balance": 5.00,
      "total_debits": 0.00,
      "total_credits": 0.00,
      "ending_balance": 5.00,
      "ytd_dividends": 0.00,
      "transactions": [
        {"date": "2025-06-01", "deposit": null, "withdrawal": null, "balance": 5.00, "description": "Beginning Balance"},
        {"date": "2025-06-30", "deposit": null, "withdrawal": null, "balance": 5.00, "description": "Ending Balance"}
      ]
    },
    {
      "account_name": "Small Business Checking",
      "account_suffix": "0075",
      "beginning_balance": 78854.89,
      "total_debits": 95933.09,
      "total_credits": 19363.99,
      "ending_balance": 2285.79,
      "ytd_dividends": 0.00,
      "transactions": [
        {"date": "2025-06-01", "deposit": null, "withdrawal": null, "balance": 78854.89, "description": "Beginning Balance"},
        {"date": "2025-06-02", "deposit": null, "withdrawal": -605.42, "balance": 78249.47, "description": "ACH Withdrawal Nav Technologies, NAVPC PYMT, Todrick Walker Nav Technologie"},
        "..."
      ]
    }
  ]
}
```

---

## 11. PARSER PROMPT (For AI-Assisted Extraction)

Use this prompt when passing OCR text to an LLM for structured extraction:

```
You are a bank statement parser for First Service Credit Union (FSCU) statements.

STATEMENT FACTS:
- Bank: First Service Credit Union
- Statement Period: 06/01/25 - 06/30/25
- Account Number: 5689715
- Customer: Walker's Total Solutions LLC

COLUMN ORDER in transaction table:
  Eff.Date | Deposit | Withdrawal | Balance | Description

RULES:
1. Extract EVERY transaction row from the Small Business Checking (0075) account.
2. Withdrawal amounts appear with a minus sign (-). Normalize misread characters:
   quote ("), apostrophe ('), backtick (`) before a number = minus sign.
3. A row has EITHER a Deposit OR a Withdrawal, never both.
4. The Description column captures everything after the Balance column — include
   all merchant names, reference codes, and trailing trace numbers.
5. Date format output: YYYY-MM-DD
6. Amount format output: numeric float (negative for withdrawals)
7. Do NOT skip any rows. There are 91 transaction rows plus Beginning/Ending Balance.
8. Validate: each row's balance = previous balance + deposit - withdrawal.
9. Output ONLY valid JSON matching the schema below.

OUTPUT SCHEMA:
{
  "transactions": [
    {
      "date": "YYYY-MM-DD",
      "deposit": <float or null>,
      "withdrawal": <float or null>,
      "balance": <float>,
      "description": "<string>"
    }
  ]
}

OCR TEXT TO PARSE:
[INSERT FULL OCR TEXT HERE]
```

---

## 12. EDGE CASES & KNOWN QUIRKS

| Quirk | Detail |
|---|---|
| **Multi-page section** | Small Business Checking spans pages 1–3. Page continuation has no repeat of section summary header. |
| **Page header repeat** | Pages 2–3 start with `(Continued)` label — skip re-parsing the section header |
| **Same-date clustering** | 06/06/25 has 16 transactions; 06/13/25 has 15 — must not collapse them |
| **Trace codes in background** | The watermark trace numbers (e.g., 515321100121) appear in the text layer at odd x-positions — these are NOT standalone transactions, they are embedded in Description column |
| **Balance on Beginning row** | The very first row shows `$ 78,854.89` in the Balance column with no Deposit or Withdrawal |
| **No Date on Continuation Rows** | Some same-day rows may have blank date — inherit date from the row immediately above |
| **Draft Recap Date Format** | Recap uses MM/DD (no year) — append statement year |
| **Out-of-sequence drafts** | Marked with `*` in the Cleared Draft Recap — flag in output |
| **Statement Fee** | `Fee Withdrawal Statement Fee` on 06/07 — amount: -$5.00 |
| **Wire Deposit** | `Deposit INCOMING WIRE - THE LCF GROUP INC` on 06/27 — amount: $8,570.00 (no ACH prefix) |
| **Truncated description** | `ACH Withdrawal LCF 8884992939, LC06271010, Walker's Total S` — description is cut off, keep as-is |
| **Draft # without Tracer** | `Draft Withdrawal Draft # 151`, `Draft Withdrawal Draft # 200`, `Draft Withdrawal Draft # 199` — no Tracer number; keep as-is |

---

## 13. TEMPLATE REGISTRATION METADATA

```yaml
template_id: FSCU_SMALL_BIZ_CHECKING_V1
bank: First Service Credit Union
bank_alias: [First Service, FSCU, First Service CU]
statement_type: Small Business Checking + Business Savings
state: TX
format: hybrid_scanned_pdf
ocr_required: true
pdfplumber_text_reliable: false
column_count: 5
date_format_in: MM/DD/YY
date_format_out: YYYY-MM-DD
currency: USD
multi_account: true
has_summary_block: true
has_draft_recap: true
has_continuation_pages: true
max_transactions_per_day: 16
sample_statement: First_Service_Bank.pdf
ground_truth_tx_count: 91
verified: true
created: 2025-06-15
```
