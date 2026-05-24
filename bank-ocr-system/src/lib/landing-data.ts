import { BarChart3, Cpu, Download, Globe, Layers, ScanLine, Shield, Table2, Upload } from "lucide-react";

export const FEATURES = [
    {
        icon: Cpu,
        title: "Smart OCR Engine",
        desc: "PaddleOCR + PP-StructureV3 powered pipeline with intelligent table detection and multi-column layout analysis.",
        color: "from-indigo-500/20 to-violet-500/20",
        iconColor: "text-indigo-400",
    },
    {
        icon: Globe,
        title: "Multi-Bank Support",
        desc: "Optimized for 10+ Indian banks — SBI, HDFC, ICICI, Axis, PNB, Kotak, and more with bank-specific parsing rules.",
        color: "from-emerald-500/20 to-teal-500/20",
        iconColor: "text-emerald-400",
    },
    {
        icon: Layers,
        title: "Batch Processing",
        desc: "Upload 17+ statements at once. Process multiple accounts simultaneously with progress tracking.",
        color: "from-amber-500/20 to-orange-500/20",
        iconColor: "text-amber-400",
    },
    {
        icon: Table2,
        title: "Consolidated Tables",
        desc: "Get per-account transaction tables plus a merged master view. Clean, structured, and ready for analysis.",
        color: "from-sky-500/20 to-cyan-500/20",
        iconColor: "text-sky-400",
    },
    {
        icon: Download,
        title: "Export Anywhere",
        desc: "One-click export to CSV and Excel. Database-ready JSON output for seamless integration.",
        color: "from-pink-500/20 to-rose-500/20",
        iconColor: "text-pink-400",
    },
    {
        icon: Shield,
        title: "Bank-Grade Security",
        desc: "Fully self-hosted. Your financial data never leaves your servers. Zero dependency on external cloud AI.",
        color: "from-purple-500/20 to-fuchsia-500/20",
        iconColor: "text-purple-400",
    },
];

export const STEPS = [
    {
        step: "01",
        title: "Upload Statements",
        desc: "Drag & drop multiple PDF or image bank statements. Supports batch upload of 17+ files at once.",
        icon: Upload,
        color: "bg-indigo-500",
    },
    {
        step: "02",
        title: "Intelligent Processing",
        desc: "Our hybrid OCR pipeline auto-detects digital vs scanned PDFs and extracts every transaction accurately.",
        icon: ScanLine,
        color: "bg-emerald-500",
    },
    {
        step: "03",
        title: "Clean Export",
        desc: "View consolidated tables per account, merge across all accounts, and export to CSV/Excel instantly.",
        icon: BarChart3,
        color: "bg-violet-500",
    },
];

export const STATS = [
    { value: 10000, suffix: "+", label: "Statements Processed" },
    { value: 99, suffix: ".2%", label: "Extraction Accuracy" },
    { value: 5, suffix: "s", label: "Avg Processing Time" },
    { value: 10, suffix: "+", label: "Banks Supported" },
];