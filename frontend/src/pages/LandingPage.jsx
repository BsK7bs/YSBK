import React from "react";
import AnimatedBackground from "./landing/AnimatedBackground";
import LandingNavbar from "./landing/LandingNavbar";
import LandingHero from "./landing/LandingHero";
import {
  TrustCounters,
  ProblemSolution,
  FeaturesGrid,
  DashboardPreview,
  HowItWorks,
  Comparison,
  Testimonials,
  Pricing,
  FAQ,
  CTABanner,
  LandingFooter,
} from "./landing/LandingSections";

/**
 * Premium enterprise SaaS landing page.
 *
 * Sections (in scroll order):
 *   1. Sticky blur-on-scroll Navbar (theme toggle)
 *   2. Hero with animated bg, floating cards, laptop dashboard mockup
 *   3. Trust counters (animate-on-view)
 *   4. Problem vs Solution split
 *   5. Features grid (10 modules)
 *   6. Live dashboard preview
 *   7. How it works timeline
 *   8. Comparison table
 *   9. Testimonials marquee
 *  10. Pricing
 *  11. FAQ (accordion)
 *  12. CTA banner
 *  13. Enterprise footer
 */
export default function LandingPage() {
  return (
    <div className="relative min-h-screen w-full text-foreground" style={{ overflowX: "clip" }} data-testid="landing-page">
      <AnimatedBackground />
      <LandingNavbar />
      <main>
        <LandingHero />
        <TrustCounters />
        <ProblemSolution />
        <FeaturesGrid />
        <DashboardPreview />
        <HowItWorks />
        <Comparison />
        <Testimonials />
        <Pricing />
        <FAQ />
        <CTABanner />
      </main>
      <LandingFooter />
    </div>
  );
}
