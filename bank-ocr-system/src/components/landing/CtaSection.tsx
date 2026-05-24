import Link from "next/link";
import { Button } from "../ui/button";
import { ArrowRight } from "lucide-react";
import { useRef } from "react";
import { motion, useInView } from "framer-motion";
import FadeInSection from "./FadeInSection";



export default function CtaSection() {
    return (
        <section className="relative bg-[#0A0B10] py-24">
            <div className="mx-auto max-w-7xl px-6">
                <FadeInSection>
                    <div className="relative overflow-hidden rounded-3xl bg-gradient-to-r from-indigo-600 via-violet-600 to-purple-600 px-8 py-16 text-center sm:px-16 animate-gradient-shift">
                        {/* Decorative orbs */}
                        <div className="pointer-events-none absolute -top-12 -left-12 h-48 w-48 rounded-full bg-white/10 blur-3xl" />
                        <div className="pointer-events-none absolute -bottom-12 -right-12 h-48 w-48 rounded-full bg-white/10 blur-3xl" />

                        <div className="relative z-10">
                            <h2 className="text-3xl font-extrabold text-white sm:text-4xl">
                                Ready to Automate Your
                                <br />
                                Bank Statement Processing?
                            </h2>
                            <p className="mx-auto mt-4 max-w-lg text-base text-indigo-100/80">
                                Join teams that save hours of manual data entry. Upload your
                                first batch of statements and see the magic.
                            </p>
                            <div className="mt-8 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
                                <Link href="/register">
                                    <Button
                                        size="lg"
                                        className="gap-2 bg-white px-8 py-6 text-base font-semibold text-indigo-600 shadow-xl hover:bg-slate-50 border-0 rounded-xl"
                                    >
                                        Get Started Free
                                        <ArrowRight className="h-4 w-4" />
                                    </Button>
                                </Link>
                                <Link href="/login">
                                    <Button
                                        size="lg"
                                        variant="ghost"
                                        className="px-8 py-6 text-base text-white/90 hover:text-white hover:bg-white/10 border border-white/20 rounded-xl"
                                    >
                                        Sign In
                                    </Button>
                                </Link>
                            </div>
                        </div>
                    </div>
                </FadeInSection>
            </div>
        </section>
    );
}
