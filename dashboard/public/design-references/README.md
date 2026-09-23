# Design references — Increment 16.2

Source, provenance, and usage-rights notes for the visual reference images used to build the
`/design/cinematic-homepage` prototype, and (see the Increment 17.2 section below) now the production
VentureGPS homepage and market pages. Read this before using any of these files anywhere beyond an
isolated, `NODE_ENV`-gated, non-production prototype.

## Files

- **`cinematic-homepage.png`** (1920×1080) — supplied directly by Jerrod as the primary visual
  benchmark for the hero: composition, dramatic lighting, typography mood, atmosphere. Depicts two
  humanoid robots and several technicians in a stylized lab setting with neon blue/purple accent
  lighting and circular HUD-style display graphics.
- **`mobile-discovery-reference.png`** (1400×1344) — supplied by Jerrod as the reference for mobile
  layout: a phone-in-hand composition showing a "Discover" screen with glassmorphism cards, a
  purple/blue/teal gradient background, and full-bleed portrait content with text overlays.
- **`editorial-composition-reference.png`** (2000×1125) — supplied by Jerrod as the reference for
  editorial storytelling/typography: a "RoboTech" product landing page with a center-aligned,
  cyan-to-purple gradient display headline, a dot-marker eyebrow pill, a gradient primary CTA pill
  paired with a dark secondary pill, and a close-up robot portrait below the fold.
- **`market-quantum-computing.png`**, **`market-climate-technology.png`**, **`market-biotech.png`**
  (554×941 each) — Increment 16.3 (Section B), used as each market's own hero image in the
  "Explore the Startup Economy" market tiles. Cropped by Claude from a single triptych image Jerrod
  supplied (a 1672×941 three-panel collage; the panel boundaries were located programmatically from
  the image's own pixel data, not eyeballed, so each crop is the panel Jerrod's own image already
  defined). Depicts, respectively: a quantum-computing lab with a cryostat apparatus and a
  researcher at a workstation; a sunset skyline with wind turbines, solar panels, and a shipping-
  container-style structure bearing "CLEAN ENERGY / BRIGHTER TOMORROW" signage; a lab researcher
  at a microscope with a DNA-helix graphic and "HEALTHIER PEOPLE / BRIGHTER FUTURES" signage on a
  background screen. Each source panel also carries its own baked-in bottom caption text (market
  name + one line) from the original triptych -- these are NOT removed from the cropped files, but
  every use of these images places VentureGPS's own glass-panel caption over that same lower
  region, so the source image's own caption is visually covered by the real UI, not double-captioned.

## Provenance and licensing — read before reuse

**All six images visually present as AI-generated / stock-template imagery**, not photography of a
real company, facility, or event. Claude did not generate any of these images.

- `mobile-discovery-reference.png` contains a placeholder social-app mockup with the name
  "Louis Tomlinson" attached to sample content — this is template/mockup text from the reference
  asset itself, not anything VentureGPS should ever display; it is cropped out of every rendered use.
- `editorial-composition-reference.png` is branded "RoboTech," a fictional product name that belongs
  to the reference template, not to VentureGPS — reused for its typography/composition technique
  (gradient headline text, pill eyebrow, gradient CTA) only, never the "RoboTech" name or logo itself.
- Neither image depicts a real robotics company, a real facility, or a real VentureGPS market — every
  prototype use carries a visible "Reference imagery" caption specifically so a viewer can never
  mistake it for real photography of a real company.

### `cinematic-homepage.png`, `market-quantum-computing.png`, `market-climate-technology.png`, `market-biotech.png` — cleared for production (Increment 17.2)

Jerrod has stated these four images were generated for him using ChatGPT (OpenAI), created
specifically for VentureGPS, and are intended for commercial website use. The rights basis he has
given: under OpenAI's terms of use, OpenAI assigns to the user whatever rights OpenAI itself may hold
in the images its models generate for that user. On that stated basis, these four images are cleared
for production use in the VentureGPS homepage and market pages (see components/home/ventureGps/ for
where each is now used).

Two things this basis explicitly does **not** claim, stated here because Jerrod asked that it not be
overstated:

- **Not a claim of exclusive copyright.** Whether, and to what extent, AI-generated output is subject
  to copyright at all is an unsettled legal question in multiple jurisdictions. This document records
  the rights-assignment basis Jerrod has stated, not a representation that VentureGPS holds exclusive
  copyright in these images.
- **Not a guarantee against third-party infringement.** OpenAI's terms do not warrant that a generated
  image is free of any third party's rights (e.g. resemblance to training data, an incidentally
  reproduced style, mark, or likeness), and Claude has no independent way to verify that no such claim
  exists. If a third-party rights concern is ever raised about one of these images, that is a separate
  question from the rights-assignment basis recorded here, and should be evaluated on its own.

`mobile-discovery-reference.png` and `editorial-composition-reference.png` are **not** covered by this
clearance — Jerrod's statement was specific to the hero and market images above. Those two remain
design-technique references only (see their own notes above: mockup/placeholder content that was never
meant to be reused as imagery), unchanged, and must not be used in production without a separate,
explicit clearance.
