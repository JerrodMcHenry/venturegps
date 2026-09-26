"use client";

import { useState } from "react";

import PillarNav from "./PillarNav";
import PillarWorkspace from "./PillarWorkspace";
import { PILLARS } from "./pillarMeta";

import type { PillarKey } from "./pillarMeta";
import type { SIEMethodologyAnalysis } from "@/types";

type IntelligencePillarsProps = {
  methodology: SIEMethodologyAnalysis;
};

export default function IntelligencePillars({
  methodology,
}: IntelligencePillarsProps) {
  const [selectedKey, setSelectedKey] = useState<PillarKey>(PILLARS[0].key);

  const selectedDefinition =
    PILLARS.find((pillar) => pillar.key === selectedKey) ?? PILLARS[0];

  return (
    <section>
      {/* Phase 10.11, Part 6/11: "Workspace" implied a private, editable
          tool -- this is a read-only public drill-down into how the
          score breaks down. Presentation only; nothing about the
          pillar/methodology data model changed.
          Portfolio Release Task 6 -- Standardize User-Facing
          Terminology: the six categories are consistently called
          "Intelligence Pillars" (SIE remains the internal engine name). */}
      <h2 className="text-xl font-semibold text-text-primary">
        The Six Intelligence Pillars
      </h2>

      <div className="mt-4 grid gap-6 lg:grid-cols-[300px_1fr] lg:items-start">
        <PillarNav
          methodology={methodology}
          selectedKey={selectedKey}
          onSelect={setSelectedKey}
        />

        <PillarWorkspace
          label={selectedDefinition.label}
          pillar={methodology[selectedDefinition.key]}
        />
      </div>
    </section>
  );
}
