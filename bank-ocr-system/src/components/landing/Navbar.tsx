import { motion, useInView } from "framer-motion";
import { ArrowRight, FileText, Menu, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "../ui/button";

export default function Navbar() {
    const [scrolled, setScrolled] = useState(false);
    const [mobileOpen, setMobileOpen] = useState(false);

    useEffect(() => {
        const onScroll = () => setScrolled(window.scrollY > 30);
        window.addEventListener("scroll", onScroll, { passive: true });
        return () => window.removeEventListener("scroll", onScroll);
    }, []);

    return (
        <motion.nav
            initial={{ y: -80 }}
            animate={{ y: 0 }}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
            className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${scrolled
                ? "bg-[#0F1117]/80 backdrop-blur-xl border-b border-white/5 shadow-lg shadow-black/10"
                : "bg-transparent"
                }`}
        >
            <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
                {/* Logo */}
                <Link href="/" className="flex items-center gap-2.5">
                    <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 shadow-lg shadow-indigo-500/25">
                        <FileText className="h-4.5 w-4.5 text-white" />
                    </div>
                    <span className="text-lg font-bold tracking-tight text-white">
                        BankOCR
                    </span>
                </Link>

                {/* Desktop Nav */}
                <div className="hidden items-center gap-8 md:flex">
                    <a
                        href="#features"
                        className="text-sm font-medium text-slate-400 transition-colors hover:text-white"
                    >
                        Features
                    </a>
                    <a
                        href="#how-it-works"
                        className="text-sm font-medium text-slate-400 transition-colors hover:text-white"
                    >
                        How It Works
                    </a>
                    <a
                        href="#pricing"
                        className="text-sm font-medium text-slate-400 transition-colors hover:text-white"
                    >
                        Pricing
                    </a>
                </div>

                {/* CTA Buttons */}
                <div className="hidden items-center gap-3 md:flex">
                    <Link href="/login">
                        <Button
                            variant="ghost"
                            className="text-sm text-slate-300 hover:text-white hover:bg-white/5"
                        >
                            Log In
                        </Button>
                    </Link>
                    <Link href="/register">
                        <Button className="gap-2 bg-gradient-to-r from-indigo-500 to-violet-600 text-sm font-semibold text-white shadow-lg shadow-indigo-500/25 hover:shadow-indigo-500/40 hover:from-indigo-400 hover:to-violet-500 border-0">
                            Get Started Free
                            <ArrowRight className="h-3.5 w-3.5" />
                        </Button>
                    </Link>
                </div>

                {/* Mobile Menu Toggle */}
                <button
                    className="md:hidden text-white"
                    onClick={() => setMobileOpen(!mobileOpen)}
                >
                    {mobileOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
                </button>
            </div>

            {/* Mobile Menu */}
            {mobileOpen && (
                <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="border-t border-white/5 bg-[#0F1117]/95 backdrop-blur-xl px-6 py-6 md:hidden"
                >
                    <div className="flex flex-col gap-4">
                        <a
                            href="#features"
                            onClick={() => setMobileOpen(false)}
                            className="text-sm font-medium text-slate-300 hover:text-white"
                        >
                            Features
                        </a>
                        <a
                            href="#how-it-works"
                            onClick={() => setMobileOpen(false)}
                            className="text-sm font-medium text-slate-300 hover:text-white"
                        >
                            How It Works
                        </a>
                        <a
                            href="#pricing"
                            onClick={() => setMobileOpen(false)}
                            className="text-sm font-medium text-slate-300 hover:text-white"
                        >
                            Pricing
                        </a>
                        <div className="flex flex-col gap-2 pt-4 border-t border-white/10">
                            <Link href="/login">
                                <Button variant="ghost" className="w-full text-slate-300 hover:text-white hover:bg-white/5">
                                    Log In
                                </Button>
                            </Link>
                            <Link href="/dashboard">
                                <Button className="w-full bg-gradient-to-r from-indigo-500 to-violet-600 text-white">
                                    Get Started Free
                                </Button>
                            </Link>
                        </div>
                    </div>
                </motion.div>
            )}
        </motion.nav>
    );
}