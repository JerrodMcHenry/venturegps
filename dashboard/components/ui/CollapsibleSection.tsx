"use client";

import { useState } from "react";
import type { ReactNode } from "react";

// Task 5 -- Unified Visual Design. Extracted from
// components/startup/PillarWorkspace.tsx's own TechnicalDetails, which
// had exactly this "quiet, collapsed-by-default, chevron-rotates" pattern
// hand-rolled once already -- generalized here so a second, unrelated
// collapsible (the AI-transparency "How this analysis was generated"
// section) reuses the same component instead of a second hand-rolled
// copy. TechnicalDetails itself now renders through this.
type CollapsibleSectionProps = {
  title: ReactNode;
  icon?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
};

export default function CollapsibleSection({
  title,
  icon,
  children,
  defaultOpen = false,
  className = "",
}: CollapsibleSectionProps) {
  const [expanded, setExpanded] = useState(defaultOpen);

  return (
    <section className={["rounded-xl bg-surface-muted", className].join(" ")}>
      <button
        type="button"
        onClick={() => setExpanded((previous) => !previous)}
        aria-expanded={expanded}
        className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left"
      >
        <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-text-secondary">
          {icon}
          {title}
        </span>
        <span
          aria-hidden="true"
          className={[
            "text-text-muted transition-transform duration-200 motion-reduce:transition-none",
            expanded ? "rotate-90" : "",
          ].join(" ")}
        >
          ▸
        </span>
      </button>

      {expanded ? <div className="space-y-4 border-t border-border px-4 py-3">{children}</div> : null}
    </section>
  );
}
