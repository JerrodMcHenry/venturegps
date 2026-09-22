import { ImageResponse } from "next/og";

import { getMarketBySlug } from "@/lib/api/v2/markets.ts";

// VentureGPS Increment 15, Part 6 -- a dynamic, per-market Open Graph image via next/og's ImageResponse (the
// file-convention route Next auto-wires into generateMetadata's <head> tags -- no manual `openGraph.images`
// entry is needed in page.tsx's generateMetadata for this to take effect). Deliberately NOT a custom image-
// generation service: this is markup/CSS rendered to a PNG at request time, using only the market's own name --
// no invented stats, no fabricated numbers, nothing beyond what the brand and the market's real display_name
// provide. Colors are hardcoded to match globals.css's dark-mode tokens 1:1 (ImageResponse/satori cannot read
// CSS custom properties or Tailwind classes, so this is the one place in the app those values are duplicated by
// hand rather than referenced).
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;

  let displayName = "Market";
  try {
    const market = await getMarketBySlug(slug);
    if (market) displayName = market.display_name;
  } catch {
    // A failed lookup still renders a generic, on-brand image rather than a broken OG request -- a crawler
    // should never see a 500 here.
  }

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "72px",
          background: "#07111f",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
          <div
            style={{
              width: "20px",
              height: "20px",
              borderRadius: "9999px",
              background: "#4f8cff",
              display: "flex",
            }}
          />
          <span style={{ fontSize: "30px", fontWeight: 700, color: "#4f8cff", letterSpacing: "-0.5px" }}>
            VentureGPS
          </span>
        </div>

        <div style={{ display: "flex", flexDirection: "column", maxWidth: "980px" }}>
          <span style={{ fontSize: "72px", fontWeight: 700, color: "#eef4ff", lineHeight: 1.1, letterSpacing: "-1.5px" }}>
            {displayName}
          </span>
          <span style={{ marginTop: "20px", fontSize: "30px", color: "#a8b6ca" }}>
            Verified Capital Intelligence, tracked over time
          </span>
        </div>

        <span style={{ fontSize: "24px", color: "#5f6b7b" }}>Navigate the Startup Economy</span>
      </div>
    ),
    { ...size }
  );
}
