import { ArrowRight, CheckCircle2 } from "lucide-react";
import FadeInSection from "./FadeInSection";
import Link from "next/link";
import { Button } from "../ui/button";
import { motion, useInView } from "framer-motion";

export default function DemoPreviewSection() {
    return (
        <section className="relative bg-[#0A0B10] py-24 overflow-hidden">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 h-px w-2/3 bg-gradient-to-r from-transparent via-white/5 to-transparent" />

            <div className="mx-auto max-w-7xl px-6">
                <div className="grid items-center gap-12 lg:grid-cols-2">
                    {/* Left - Text */}
                    <FadeInSection>
                        <p className="text-sm font-semibold uppercase tracking-widest text-indigo-400 mb-4">
                            Built for Indian Banks
                        </p>
                        <h2 className="text-3xl font-extrabold tracking-tight text-white sm:text-4xl">
                            Handles Every
                            <span className="text-gradient"> Format & Layout</span>
                        </h2>
                        <p className="mt-4 text-base leading-relaxed text-slate-400">
                            Our hybrid pipeline intelligently switches between digital text
                            extraction and OCR-based scanning. Whether your statement is a
                            clean digital PDF from HDFC NetBanking or a scanned photocopy from
                            SBI, we handle it all.
                        </p>
                        <ul className="mt-6 space-y-3">
                            {[
                                "Digital PDFs — PyMuPDF + pdfplumber (instant)",
                                "Scanned PDFs — PaddleOCR fallback (AI-powered)",
                                "Multi-column layouts & wrapped rows",
                                "Date, amount, and narration normalization",
                            ].map((item) => (
                                <li
                                    key={item}
                                    className="flex items-start gap-3 text-sm text-slate-300"
                                >
                                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                                    {item}
                                </li>
                            ))}
                        </ul>
                        <div className="mt-8">
                            <Link href="/register">
                                <Button className="gap-2 bg-gradient-to-r from-indigo-500 to-violet-600 text-white shadow-lg shadow-indigo-500/25 border-0">
                                    Try It Now <ArrowRight className="h-4 w-4" />
                                </Button>
                            </Link>
                        </div>
                    </FadeInSection>

                    {/* Right - Bank logos / Preview */}
                    <FadeInSection delay={0.2}>
                        <div className="relative">
                            {/* Background glow */}
                            <div className="absolute -inset-8 rounded-3xl bg-gradient-to-br from-indigo-500/10 to-violet-500/10 blur-3xl" />

                            <div className="relative rounded-2xl border border-white/[0.06] bg-white/[0.02] p-8">
                                <div className="mb-6">
                                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-4">
                                        Supported Banks
                                    </p>
                                    <div className="flex flex-wrap gap-2">
                                        {[
                                            "SBI",
                                            "HDFC",
                                            "ICICI",
                                            "Axis",
                                            "PNB",
                                            "Kotak",
                                            "IndusInd",
                                            "Yes Bank",
                                            "Bank of Baroda",
                                            "Union Bank",
                                        ].map((bank) => (
                                            <span
                                                key={bank}
                                                className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs font-medium text-slate-300"
                                            >
                                                {bank}
                                            </span>
                                        ))}
                                    </div>
                                </div>

                                <div className="space-y-3">
                                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                                        Processing Pipeline
                                    </p>
                                    {[
                                        { label: "PDF Detection", status: "Digital / Scanned", pct: 100 },
                                        { label: "Text Extraction", status: "PaddleOCR v4", pct: 95 },
                                        { label: "Table Parsing", status: "PP-StructureV3", pct: 92 },
                                        { label: "Post-Processing", status: "Rule Engine", pct: 98 },
                                    ].map((row) => (
                                        <div key={row.label}>
                                            <div className="flex justify-between text-xs mb-1">
                                                <span className="text-slate-400">{row.label}</span>
                                                <span className="text-slate-500">{row.status}</span>
                                            </div>
                                            <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                                                <motion.div
                                                    initial={{ width: 0 }}
                                                    whileInView={{ width: `${row.pct}%` }}
                                                    viewport={{ once: true }}
                                                    transition={{ duration: 1.2, delay: 0.3, ease: "easeOut" }}
                                                    className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500"
                                                />
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </FadeInSection>
                </div>
            </div>
        </section>
    );
}