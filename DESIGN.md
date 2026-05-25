# Design Specification: Advanced OCR Extraction System

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI Backend                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐  │
│  │   Upload     │─────▶│  PDF Service │─────▶│ OCR Service  │  │
│  │   Endpoint   │      │              │      │              │  │
│  └──────────────┘      └──────────────┘      └──────────────┘  │
│                                                      │            │
│                                                      ▼            │
│                        ┌─────────────────────────────────┐       │
│                        │  Enhanced Extraction Pipeline   │       │
│                        ├─────────────────────────────────┤       │
│                        │  1. Text Extraction             │       │
│                        │  2. Table Detection             │       │
│                        │  3. Section Detection           │       │
│                        │  4. Column Mapping              │       │
│                        │  5. Transaction Extraction      │       │
│                        │  6. Validation & Reconciliation │       │
│                        │  7. Confidence Scoring          │       │
│                        └─────────────────────────────────┘       │
│                                      │                            │
│                                      ▼                            │
│                        ┌─────────────────────────────────┐       │
│                        │   Structured Transaction Data   │       │
│                        └─────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

### Component Diagram

```
┌────────────────────────────────────────────────────────────────┐
│                    OCR Service (Orchestrator)                   │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────────┐
        │                                             │
        ▼                                             ▼
┌──────────────────┐                      ┌──────────────────┐
│  TextExtractor   │                      │  TableDetector   │
│  - pdfplumber    │                      │  - Detect tables │
│  - pytesseract   │                      │  - Find columns  │
└──────────────────┘                      └──────────────────┘
        │                                             │
        └─────────────────┬───────────────────────────┘
                          ▼
              ┌──────────────────────┐
              │  SectionDetector     │
              │  - Find DEPOSITS     │
              │  - Find WITHDRAWALS  │
              └──────────────────────┘
                          │
                          ▼
              ┌──────────────────────┐
              │   ColumnMapper       │
              │   - Map Date col     │
              │   - Map Amount col   │
              │   - Map Desc col     │
              └──────────────────────┘
                          │
                          ▼
              ┌──────────────────────┐
              │ TransactionExtractor │
              │ - Parse dates        │
              │ - Extract amounts    │
              │ - Classify type      │
              └──────────────────────┘
                          │
                          ▼
              ┌──────────────────────┐
              │  BalanceReconciler   │
              │  - Validate totals   │
              │  - Check consistency │
              └──────────────────────┘
                          │
                          ▼
              ┌──────────────────────┐
              │  ConfidenceScorer    │
              │  - Score each field  │
              │  - Flag low quality  │
              └──────────────────────┘
```

