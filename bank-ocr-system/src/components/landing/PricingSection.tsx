import { CheckCircle2 } from "lucide-react";
import FadeInSection from "./FadeInSection";
import Link from "next/link";
import { Button } from "../ui/button";

export default function PricingSection() {
    return (
        <section id="pricing" className="relative bg-[#0A0B10] py-24">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 h-px w-2/3 bg-gradient-to-r from-transparent via-white/5 to-transparent" />

            <div className="mx-auto max-w-7xl px-6">
                <FadeInSection className="text-center mb-16">
                    <p className="text-sm font-semibold uppercase tracking-widest text-indigo-400 mb-3">
                        Pricing
                    </p>
                    <h2 className="text-3xl font-extrabold tracking-tight text-white sm:text-4xl">
                        Simple,
                        <span className="text-gradient"> Transparent Pricing</span>
                    </h2>
                    <p className="mx-auto mt-4 max-w-lg text-base text-slate-400">
                        Self-hosted means near-zero marginal cost. Process thousands of
                        statements for a fraction of what cloud APIs charge.
                    </p>
                </FadeInSection>

                <div className="mx-auto grid max-w-4xl gap-6 md:grid-cols-2">
                    {/* Free Tier */}
                    <FadeInSection delay={0.1}>
                        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-8">
                            <p className="text-sm font-semibold text-slate-400">Starter</p>
                            <div className="mt-3 flex items-baseline gap-1">
                                <span className="text-4xl font-extrabold text-white">Free</span>
                            </div>
                            <p className="mt-2 text-sm text-slate-500">
                                Perfect for testing and small batches
                            </p>

                            <ul className="mt-6 space-y-3">
                                {[
                                    "Up to 10 statements/month",
                                    "All supported banks",
                                    "CSV export",
                                    "Basic dashboard",
                                    "Community support",
                                ].map((item) => (
                                    <li
                                        key={item}
                                        className="flex items-center gap-2.5 text-sm text-slate-300"
                                    >
                                        <CheckCircle2 className="h-4 w-4 text-slate-500" />
                                        {item}
                                    </li>
                                ))}
                            </ul>

                            <Link href="/login" className="block mt-8">
                                <Button
                                    variant="outline"
                                    className="w-full border-white/10 text-white hover:bg-white/5"
                                >
                                    Get Started
                                </Button>
                            </Link>
                        </div>
                    </FadeInSection>

                    {/* Pro Tier */}
                    <FadeInSection delay={0.2}>
                        <div className="relative rounded-2xl border border-indigo-500/30 bg-gradient-to-b from-indigo-500/5 to-transparent p-8">
                            {/* Popular badge */}
                            <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-gradient-to-r from-indigo-500 to-violet-600 px-4 py-1 text-xs font-semibold text-white shadow-lg shadow-indigo-500/25">
                                Most Popular
                            </div>

                            <p className="text-sm font-semibold text-indigo-400">Pro</p>
                            <div className="mt-3 flex items-baseline gap-1">
                                <span className="text-4xl font-extrabold text-white">
                                    &lt;10¢
                                </span>
                                <span className="text-sm text-slate-500">/statement</span>
                            </div>
                            <p className="mt-2 text-sm text-slate-500">
                                For teams processing at scale
                            </p>

                            <ul className="mt-6 space-y-3">
                                {[
                                    "Unlimited statements",
                                    "Priority processing (GPU)",
                                    "Excel + JSON export",
                                    "Full analytics dashboard",
                                    "API access",
                                    "Priority support",
                                    "Custom bank format support",
                                ].map((item) => (
                                    <li
                                        key={item}
                                        className="flex items-center gap-2.5 text-sm text-slate-300"
                                    >
                                        <CheckCircle2 className="h-4 w-4 text-indigo-400" />
                                        {item}
                                    </li>
                                ))}
                            </ul>

                            <Link href="/register" className="block mt-8">
                                <Button className="w-full bg-gradient-to-r from-indigo-500 to-violet-600 text-white border-0 shadow-lg shadow-indigo-500/25">
                                    Start Free Trial
                                </Button>
                            </Link>
                        </div>
                    </FadeInSection>
                </div>
            </div>
        </section>
    );
}