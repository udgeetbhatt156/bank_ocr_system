import FadeInSection from "./FadeInSection";
import { FEATURES } from "@/lib/landing-data";

export default function FeaturesSection() {
    return (
        <section id="features" className="relative bg-[#0A0B10] py-24">
            {/* Subtle divider glow */}
            <div className="absolute top-0 left-1/2 -translate-x-1/2 h-px w-2/3 bg-gradient-to-r from-transparent via-indigo-500/20 to-transparent" />

            <div className="mx-auto max-w-7xl px-6">
                <FadeInSection className="text-center mb-16">
                    <p className="text-sm font-semibold uppercase tracking-widest text-indigo-400 mb-3">
                        Features
                    </p>
                    <h2 className="text-3xl font-extrabold tracking-tight text-white sm:text-4xl">
                        Everything You Need for
                        <br />
                        <span className="text-gradient">Bank Statement Processing</span>
                    </h2>
                    <p className="mx-auto mt-4 max-w-xl text-base text-slate-400">
                        A complete, self-hosted OCR pipeline built for Indian bank
                        statements. Fast, accurate, and cost-effective.
                    </p>
                </FadeInSection>

                <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
                    {FEATURES.map((feature, i) => (
                        <FadeInSection key={feature.title} delay={i * 0.08}>
                            <div className="group relative overflow-hidden rounded-2xl border border-white/[0.06] bg-white/[0.02] p-7 transition-all duration-300 hover:border-indigo-500/20 hover:bg-white/[0.04] hover:shadow-lg hover:shadow-indigo-500/5">
                                {/* Gradient hover overlay */}
                                <div
                                    className={`pointer-events-none absolute -top-20 -right-20 h-40 w-40 rounded-full bg-gradient-to-br ${feature.color} opacity-0 blur-3xl transition-opacity duration-500 group-hover:opacity-100`}
                                />

                                <div className="relative">
                                    <div
                                        className={`mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-white/[0.05] ${feature.iconColor}`}
                                    >
                                        <feature.icon className="h-6 w-6" />
                                    </div>
                                    <h3 className="text-lg font-semibold text-white">
                                        {feature.title}
                                    </h3>
                                    <p className="mt-2 text-sm leading-relaxed text-slate-400">
                                        {feature.desc}
                                    </p>
                                </div>
                            </div>
                        </FadeInSection>
                    ))}
                </div>
            </div>
        </section>
    );
}