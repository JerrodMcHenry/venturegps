// VentureGPS Increment 16 -- the Discover prototype's top-level composition. A plain composition root (no state
// of its own; SignalsRail owns its own interactivity) so each section stays independently readable and, per the
// Blueprint doc's "challenge the hierarchy" instruction, independently removable if a future review decides a
// section doesn't earn its place.
import PrototypeBanner from "./PrototypeBanner";
import DiscoverNavConcept from "./DiscoverNavConcept";
import HeroFeatured from "./HeroFeatured";
import SignalsRail from "./SignalsRail";
import ExploreMarketsSection from "./ExploreMarketsSection";
import BriefSection from "./BriefSection";
import ClosingSection from "./ClosingSection";

import { SAMPLE_MARKET_SIGNALS, SAMPLE_STORIES } from "./sampleData";

export default function DiscoverPrototype() {
  return (
    <div>
      <PrototypeBanner />
      <DiscoverNavConcept />
      <HeroFeatured featured={SAMPLE_MARKET_SIGNALS[0]} />
      <SignalsRail markets={SAMPLE_MARKET_SIGNALS} />
      <ExploreMarketsSection markets={SAMPLE_MARKET_SIGNALS} />
      <BriefSection stories={SAMPLE_STORIES} />
      <ClosingSection />
    </div>
  );
}
