import CinematicPrototypeDisclaimer from "./CinematicPrototypeDisclaimer";
import CinematicHero from "./CinematicHero";
import SectionB from "./sectionB/SectionB";

// VentureGPS Increment 16.2/16.3 -- Cinematic Homepage. The hero (CinematicHero) is approved and untouched by
// this increment; Section B ("Explore the Startup Economy") is added immediately below it. The full-width
// PrototypeRibbon banner used by every other /design/* route is replaced here with a small, fixed corner
// disclaimer (CinematicPrototypeDisclaimer) so nothing competes with the hero's first viewport -- scoped to this
// one component tree; PrototypeRibbon itself, and every other prototype using it, is unchanged.
export default function CinematicHomepage() {
  return (
    <div>
      <CinematicPrototypeDisclaimer />
      <CinematicHero />
      <SectionB />
    </div>
  );
}
