import SectionBIntro from "./SectionBIntro";
import MarketShowcaseDesktop from "./MarketShowcaseDesktop";
import MarketCarouselMobile from "./MarketCarouselMobile";

// VentureGPS Increment 16.3 -- "Explore the Startup Economy," immediately below the approved hero. Two
// interaction components, not one shared one: MarketShowcaseDesktop (`hidden lg:grid`) and
// MarketCarouselMobile (`lg:hidden`) are genuinely different UIs for genuinely different interaction models
// (click-to-feature vs. swipe), not one component awkwardly reshaping itself per breakpoint. Only one is ever
// visible at a time via CSS, and each keeps its own independent state -- no cross-breakpoint state to
// synchronize, since a visitor is only ever looking at one of them.
export default function SectionB() {
  return (
    <section aria-labelledby="section-b-heading" className="bg-background">
      <SectionBIntro />
      <MarketShowcaseDesktop />
      <div className="pb-16">
        <MarketCarouselMobile />
      </div>
    </section>
  );
}
