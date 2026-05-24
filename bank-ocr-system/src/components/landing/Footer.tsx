import { FileText } from "lucide-react";

const FOOTER_LINKS = {
    Product: [
        { label: "Features", href: "#features" },
        { label: "How it works", href: "#how-it-works" },
        { label: "Pricing", href: "#pricing" },
        { label: "API access", href: "#" },
        { label: "Changelog", href: "#" },
    ],
    Banks: [
        { label: "SBI", href: "#" },
        { label: "HDFC", href: "#" },
        { label: "ICICI", href: "#" },
        { label: "Axis Bank", href: "#" },
        { label: "View all →", href: "#" },
    ],
    Company: [
        { label: "About", href: "#" },
        { label: "Blog", href: "#" },
        { label: "Privacy policy", href: "#" },
        { label: "Terms of service", href: "#" },
        { label: "Contact", href: "#" },
    ],
};

export default function Footer() {
    return (
        <footer className="bg-[#080910] border-t border-white/5">
            <div className="mx-auto max-w-7xl px-6 pt-14 pb-8">
                <div className="grid grid-cols-2 gap-10 sm:grid-cols-4">
                    {/* Logo & Description */}
                    <div className="col-span-2 sm:col-span-1">
                        <div className="flex items-center gap-2.5 mb-3">
                            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600">
                                <FileText className="h-4 w-4 text-white" />
                            </div>
                            <span className="text-base font-bold text-white">BankOCR</span>
                        </div>
                        <p className="text-sm text-slate-400 leading-relaxed max-w-[220px] mb-4">
                            Extract structured transactions from Indian bank statements in
                            seconds. Self-hosted, secure, and accurate.
                        </p>
                        <div className="flex flex-wrap gap-2">
                            {["PaddleOCR", "PP-StructureV3", "Open Source"].map((tag) => (
                                <span
                                    key={tag}
                                    className="rounded-md border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[11px] font-medium text-slate-400"
                                >
                                    {tag}
                                </span>
                            ))}
                        </div>
                    </div>

                    {/* Links Sections */}
                    {Object.entries(FOOTER_LINKS).map(([heading, links]) => (
                        <div key={heading}>
                            <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-500 mb-4">
                                {heading}
                            </p>
                            <ul className="space-y-2.5">
                                {links.map((link) => (
                                    <li key={link.label}>
                                        <a
                                            href={link.href}
                                            className="text-sm text-slate-400 hover:text-white transition-colors"
                                        >
                                            {link.label}
                                        </a>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    ))}
                </div>
            </div>

            {/* Bottom Bar */}
            <div className="mx-auto max-w-7xl border-t border-white/5 px-6 py-5">
                <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
                    <p className="text-xs text-slate-600">
                        © {new Date().getFullYear()} BankOCR by PokerTrac. All rights reserved.
                    </p>

                    <div className="flex items-center gap-1.5 rounded-full border border-white/5 bg-white/[0.02] px-3 py-1">
                        <span className="relative flex h-1.5 w-1.5">
                            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
                            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
                        </span>
                        <span className="text-[11px] text-slate-500">All systems operational</span>
                    </div>

                    {/* Social Links */}
                    <div className="flex items-center gap-2">
                        {[
                            { label: "GitHub", href: "#" },
                            { label: "Twitter", href: "#" },
                            { label: "LinkedIn", href: "#" },
                        ].map((s) => (
                            <a
                                key={s.label}
                                href={s.href}
                                aria-label={s.label}
                                className="flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-white/[0.03] text-slate-400 hover:text-white hover:border-white/20 transition-all"
                            >
                                <span className="text-xs font-medium">{s.label[0]}</span>
                            </a>
                        ))}
                    </div>
                </div>
            </div>
        </footer>
    );
}