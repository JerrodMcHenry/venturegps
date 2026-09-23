import Image from "next/image";

import { marketImageFor } from "./marketImages";
import { cardPlaceholderClass } from "./cardPlaceholder";

// VentureGPS Increment 17.2 -- shared by MarketShowcaseDesktop.tsx and MarketCarouselMobile.tsx (this file
// exists so that conditional isn't duplicated in both). Real, approved imagery (marketImages.ts) when this
// market's slug has one; the rights-clear gradient placeholder (cardPlaceholder.ts) otherwise -- a real market
// the approved image set doesn't cover yet gets an honest placeholder, never another market's photo and never a
// fabricated one of its own.
type MarketCardBackgroundProps = {
  slug: string;
  index: number;
  sizes: string;
};

export default function MarketCardBackground({ slug, index, sizes }: MarketCardBackgroundProps) {
  const image = marketImageFor(slug);

  if (!image) {
    return <div aria-hidden="true" className={["absolute inset-0", cardPlaceholderClass(index)].join(" ")} />;
  }

  return (
    <Image
      src={image.src}
      alt=""
      fill
      sizes={sizes}
      className="object-cover"
      style={{ objectPosition: image.objectPosition }}
    />
  );
}
