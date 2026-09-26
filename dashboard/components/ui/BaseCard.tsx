import type { HTMLAttributes, ReactNode } from "react";

// Design System V2 (Phase 10.4), Part 6: added `variant` -- three surfaces
// (Part 6: "not ten card variants"), not a rewrite. `variant` defaults to
// "default", whose className is byte-for-byte the same string this
// component always returned, so every one of the 30 existing BaseCard
// call sites across dashboard/ renders identically, unchanged.
//
// Task 5 -- Unified Visual Design: added a fourth surface, "glass" --
// the restrained glassmorphism (translucent surface + backdrop-blur +
// soft gradient border) the cinematic homepage hero already uses
// (VentureGpsHero.tsx's own glass panel), now reusable for the one or
// two "hero-adjacent" moments per page this task asks for (a page's own
// top summary card), rather than each route hand-rolling its own
// backdrop-blur/border combination. Every existing call site is
// unaffected -- this is purely additive, a fourth key in the same
// Record, not a change to "default"/"raised"/"subtle".
export type BaseCardVariant = "default" | "raised" | "subtle" | "glass";

const VARIANT_CLASSES: Record<BaseCardVariant, string> = {
  default: "rounded-2xl border border-border bg-surface shadow-sm",
  raised: "rounded-2xl border border-border bg-surface-raised shadow-md",
  subtle: "rounded-2xl border border-border bg-surface-subtle",
  glass:
    "rounded-2xl border border-primary/15 bg-surface/70 shadow-lg shadow-primary/5 backdrop-blur-xl supports-[backdrop-filter]:bg-surface/60",
};

type BaseCardProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode;
  variant?: BaseCardVariant;
};

export default function BaseCard({
  children,
  className = "",
  variant = "default",
  ...props
}: BaseCardProps) {
  return (
    <div className={[VARIANT_CLASSES[variant], className].join(" ")} {...props}>
      {children}
    </div>
  );
}
