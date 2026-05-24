import { motion, useInView } from "framer-motion";
import { ArrowRight, ChevronRight, FileText, Menu, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "../ui/button";
export default function HeroSection() {
    return (
        <section className="relative min-h-screen flex items-center justify-center overflow-hidden bg-[#0A0B10] pt-16">
            {/* Gradient orbs */}
            <div className="pointer-events-none absolute inset-0">
                <div className="absolute top-1/4 left-1/4 h-[500px] w-[500px] rounded-full bg-indigo-600/15 blur-[120px] animate-float-slow" />
                <div className="absolute bottom-1/4 right-1/4 h-[400px] w-[400px] rounded-full bg-violet-600/12 blur-[100px] animate-float" />
                <div className="absolute top-1/2 left-1/2 h-[300px] w-[300px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-indigo-500/8 blur-[80px]" />
            </div>

            {/* Grid pattern overlay */}
            <div
                className="pointer-events-none absolute inset-0 opacity-[0.03]"
                style={{
                    backgroundImage:
                        "linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)",
                    backgroundSize: "60px 60px",
                }}
            />

            <div className="relative z-10 mx-auto max-w-7xl px-6 py-20 text-center">
                {/* Badge */}
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6 }}
                    className="mb-8 inline-flex items-center gap-2 rounded-full border border-indigo-500/20 bg-indigo-500/10 px-4 py-1.5 text-sm font-medium text-indigo-300"
                >
                    <span className="relative flex h-2 w-2">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-75" />
                        <span className="relative inline-flex h-2 w-2 rounded-full bg-indigo-500" />
                    </span>
                    Powered by Open-Source OCR — PaddleOCR + PP-StructureV3
                </motion.div>

                {/* Headline */}
                <motion.h1
                    initial={{ opacity: 0, y: 30 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.7, delay: 0.15 }}
                    className="mx-auto max-w-4xl text-4xl font-extrabold leading-[1.1] tracking-tight text-white sm:text-5xl md:text-6xl lg:text-7xl"
                >
                    Extract Transactions
                    <br />
                    from Bank Statements
                    <br />
                    <span className="text-gradient">in Seconds</span>
                </motion.h1>

                {/* Subtitle */}
                <motion.p
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.7, delay: 0.3 }}
                    className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-slate-400 sm:text-lg"
                >
                    Upload 20+ bank statements from multiple accounts and get clean,
                    structured financial data instantly. Self-hosted, secure, and under
                    10¢ per statement.
                </motion.p>

                {/* CTA Buttons */}
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6, delay: 0.45 }}
                    className="mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center"
                >
                    <Link href="/register">
                        <Button
                            size="lg"
                            className="group gap-2.5 bg-gradient-to-r from-indigo-500 to-violet-600 px-8 py-6 text-base font-semibold text-white shadow-2xl shadow-indigo-500/25 hover:shadow-indigo-500/40 hover:from-indigo-400 hover:to-violet-500 border-0 rounded-xl"
                        >
                            Start Processing Free
                            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                        </Button>
                    </Link>
                    <a href="#how-it-works">
                        <Button
                            size="lg"
                            variant="ghost"
                            className="gap-2 px-8 py-6 text-base font-medium text-slate-300 hover:text-white hover:bg-white/5 rounded-xl border border-white/10"
                        >
                            See How It Works
                            <ChevronRight className="h-4 w-4" />
                        </Button>
                    </a>
                </motion.div>

                {/* Hero Visual — Dashboard Mockup */}
                <motion.div
                    initial={{ opacity: 0, y: 60, scale: 0.95 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    transition={{ duration: 0.9, delay: 0.6, ease: [0.22, 1, 0.36, 1] }}
                    className="relative mx-auto mt-16 max-w-5xl"
                >
                    {/* Glow behind mockup */}
                    <div className="absolute -inset-4 rounded-3xl bg-gradient-to-r from-indigo-500/20 via-violet-500/10 to-purple-500/20 blur-3xl" />

                    {/* Mockup Card */}
                    <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-[#1A1D2B] shadow-2xl">
                        {/* Top bar */}
                        <div className="flex items-center gap-2 border-b border-white/5 bg-[#141620] px-4 py-3">
                            <div className="flex gap-1.5">
                                <div className="h-3 w-3 rounded-full bg-red-500/60" />
                                <div className="h-3 w-3 rounded-full bg-yellow-500/60" />
                                <div className="h-3 w-3 rounded-full bg-green-500/60" />
                            </div>
                            <div className="ml-4 flex-1 rounded-md bg-white/5 px-3 py-1 text-xs text-slate-500">
                                bankocr.app/dashboard
                            </div>
                        </div>

                        {/* Dashboard Preview Content */}
                        <div className="p-6">
                            {/* Mini summary cards */}
                            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                                {[
                                    { label: "Statements", value: "10", color: "text-indigo-400" },
                                    { label: "Total Credits", value: "₹8,42,300", color: "text-emerald-400" },
                                    { label: "Total Debits", value: "₹3,18,750", color: "text-rose-400" },
                                    { label: "Net Flow", value: "₹5,23,550", color: "text-violet-400" },
                                ].map((card) => (
                                    <div
                                        key={card.label}
                                        className="rounded-xl border border-white/5 bg-white/[0.03] p-4"
                                    >
                                        <p className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
                                            {card.label}
                                        </p>
                                        <p className={`mt-1 text-lg font-bold ${card.color}`}>
                                            {card.value}
                                        </p>
                                    </div>
                                ))}
                            </div>

                            {/* Mini table */}
                            <div className="mt-4 overflow-hidden rounded-xl border border-white/5">
                                <table className="w-full text-xs">
                                    <thead>
                                        <tr className="border-b border-white/5 bg-white/[0.02]">
                                            <th className="px-4 py-2.5 text-left font-medium text-slate-500">Date</th>
                                            <th className="px-4 py-2.5 text-left font-medium text-slate-500">Description</th>
                                            <th className="px-4 py-2.5 text-right font-medium text-slate-500">Debit</th>
                                            <th className="px-4 py-2.5 text-right font-medium text-slate-500">Credit</th>
                                            <th className="px-4 py-2.5 text-right font-medium text-slate-500">Balance</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {[
                                            { date: "15/04/2026", desc: "NEFT-HDFC-SALARY APR", debit: "", credit: "₹85,000", balance: "₹1,42,350", type: "credit" },
                                            { date: "16/04/2026", desc: "UPI/408512349/Amazon", debit: "₹2,499", credit: "", balance: "₹1,39,851", type: "debit" },
                                            { date: "18/04/2026", desc: "IMPS-SBI-RENT APRIL", debit: "₹18,000", credit: "", balance: "₹1,21,851", type: "debit" },
                                            { date: "20/04/2026", desc: "NEFT-FREELANCE-INV042", debit: "", credit: "₹35,000", balance: "₹1,56,851", type: "credit" },
                                        ].map((row, i) => (
                                            <tr
                                                key={i}
                                                className="border-b border-white/[0.03] last:border-0"
                                            >
                                                <td className="px-4 py-2.5 text-slate-400">{row.date}</td>
                                                <td className="px-4 py-2.5 text-slate-300">{row.desc}</td>
                                                <td className="px-4 py-2.5 text-right text-rose-400">{row.debit || "—"}</td>
                                                <td className="px-4 py-2.5 text-right text-emerald-400">{row.credit || "—"}</td>
                                                <td className="px-4 py-2.5 text-right text-slate-400">{row.balance}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        {/* Scanning overlay effect */}
                        <div className="pointer-events-none absolute inset-0 overflow-hidden">
                            <div className="absolute left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-indigo-500/60 to-transparent animate-scan-line" />
                        </div>
                    </div>
                </motion.div>
            </div>

            {/* Bottom fade */}
            <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-[#0A0B10] to-transparent" />
        </section>
    );
}