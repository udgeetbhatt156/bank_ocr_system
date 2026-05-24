"use client";

import Navbar from "@/components/landing/Navbar";
import HeroSection from "@/components/landing/HeroSection";
import Footer from "@/components/landing/Footer";
import CtaSection from "@/components/landing/CtaSection";
import PricingSection from "@/components/landing/PricingSection";
import DemoPreviewSection from "@/components/landing/DemoPreviewSection";
import StatsBar from "@/components/landing/StatsBar";
import FeaturesSection from "@/components/landing/FeaturesSection";
import HowItWorksSection from "@/components/landing/HowItWorksSection";


export default function LandingPage() {
    return (
        <div className="min-h-screen bg-[#0A0B10]">
            <Navbar />
            <HeroSection />
            <StatsBar />
            <FeaturesSection />
            <HowItWorksSection />
            <DemoPreviewSection />
            <PricingSection />
            <CtaSection />
            <Footer />
        </div>
    );
}
