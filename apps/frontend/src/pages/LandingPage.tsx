import { HeroStub } from '../features/landing/HeroStub'
import { QuickAccess } from '../features/landing/QuickAccess'
import { TrustStrip } from '../features/landing/TrustStrip'
import { ProductCards } from '../features/landing/ProductCards'
import { FeatureShowcase } from '../features/landing/FeatureShowcase'
import { HowItWorks } from '../features/landing/HowItWorks'
import { InsightSection } from '../features/landing/InsightSection'
import { Testimonials } from '../features/landing/Testimonials'
import { FaqSection } from '../features/landing/FaqSection'
import { CtaBand } from '../features/landing/CtaBand'
import { SiteFooter } from '../features/landing/SiteFooter'
import { MistBackground } from '../features/landing/MistBackground'

export function LandingPage() {
  return (
    <>
      <MistBackground />
      <main className="relative z-10">
        <HeroStub />
        <QuickAccess />
        <TrustStrip />
        <ProductCards />
        <FeatureShowcase />
        <HowItWorks />
        <InsightSection />
        <Testimonials />
        <FaqSection />
        <CtaBand />
      </main>
      <SiteFooter />
    </>
  )
}
