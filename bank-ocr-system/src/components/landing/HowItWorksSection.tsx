import { STEPS } from "@/lib/landing-data";
import FadeInSection from "./FadeInSection";

export default function HowItWorksSection() {
    return (
        <section id="how-it-works" className="relative bg-[#0A0B10] py-24">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 h-px w-2/3 bg-gradient-to-r from-transparent via-white/5 to-transparent" />

            <div className="mx-auto max-w-7xl px-6">
                <FadeInSection className="text-center mb-16">
                    <p className="text-sm font-semibold uppercase tracking-widest text-indigo-400 mb-3">
                        How It Works
                    </p>
                    <h2 className="text-3xl font-extrabold tracking-tight text-white sm:text-4xl">
                        Three Steps to
                        <span className="text-gradient"> Clean Data</span>
                    </h2>
                </FadeInSection>

                <div className="relative grid gap-8 md:grid-cols-3">
                    {/* Connecting line (desktop) */}
                    <div className="pointer-events-none absolute top-24 left-[16%] right-[16%] hidden h-px bg-gradient-to-r from-indigo-500/30 via-emerald-500/30 to-violet-500/30 md:block" />

                    {STEPS.map((step, i) => (
                        <FadeInSection key={step.step} delay={i * 0.15}>
                            <div className="relative flex flex-col items-center text-center">
                                {/* Step number circle */}
                                <div
                                    className={`relative mb-6 flex h-16 w-16 items-center justify-center rounded-2xl ${step.color} shadow-lg shadow-${step.color}/25`}
                                >
                                    <step.icon className="h-7 w-7 text-white" />
                                    <span className="absolute -top-2 -right-2 flex h-6 w-6 items-center justify-center rounded-full bg-[#1A1D2B] text-xs font-bold text-white ring-2 ring-white/10">
                                        {step.step}
                                    </span>
                                </div>
                                <h3 className="text-xl font-bold text-white">{step.title}</h3>
                                <p className="mt-2 max-w-xs text-sm text-slate-400">
                                    {step.desc}
                                </p>
                            </div>
                        </FadeInSection>
                    ))}
                </div>
            </div>
        </section>
    );
}
