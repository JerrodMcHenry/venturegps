import type { CapitalDirection } from "@/types/v2/capital";

// The shape MarketShowcaseDesktop/MarketCarouselMobile actually need, derived from real HomepageMarket data
// (homepageData.ts) by MarketDiscoverySection.tsx. `direction: null` means this market's Capital Signal was
// unavailable (a real service/coverage gap) -- never a fabricated or defaulted direction.
export type MarketDiscoveryCard = {
  slug: string;
  displayName: string;
  direction: CapitalDirection | null;
};
