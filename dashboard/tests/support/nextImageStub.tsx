// Test-only stub for next/image, used solely by tests/support/tsxLoader.mjs to let Section B's real component
// tree render outside the Next.js app runtime (which next/image's real implementation requires -- image
// optimization, a configured loader, etc.). Renders a plain <img>, dropping Next-specific props (`fill`,
// `sizes`) that have no DOM equivalent; every prop that matters for the interaction tests we care about (src,
// alt, style, className) passes through unchanged.
import * as React from "react";

type StubImageProps = {
  src: unknown;
  alt: string;
  fill?: boolean;
  sizes?: string;
  className?: string;
  style?: React.CSSProperties;
};

export default function StubImage({ src, alt, className, style }: StubImageProps) {
  const resolvedSrc = typeof src === "string" ? src : "stub-image";
  return React.createElement("img", { src: resolvedSrc, alt, className, style });
}
