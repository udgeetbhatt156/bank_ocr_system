import { STATS } from "@/lib/landing-data";
import FadeInSection from "./FadeInSection";
import useCounter from "@/hooks/use-counter";

export default function StatsBar() {
    return (
        <section className="relative bg-[#0A0B10] py-16">
            <div className="mx-auto max-w-7xl px-6">
                <FadeInSection>
                    <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
                        {STATS.map((stat) => {
                            const { count, ref } = useCounter(stat.value);
                            return (
                                <div key={stat.label} className="text-center">
                                    <p className="text-3xl font-extrabold text-white sm:text-4xl">
                                        <span ref={ref}>{count.toLocaleString()}</span>
                                        <span className="text-indigo-400">{stat.suffix}</span>
                                    </p>
                                    <p className="mt-1.5 text-sm text-slate-500">{stat.label}</p>
                                </div>
                            );
                        })}
                    </div>
                </FadeInSection>
            </div>
        </section>
    );
}