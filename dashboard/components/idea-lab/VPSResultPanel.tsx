import BaseCard from "@/components/ui/BaseCard";
import Disclosure from "@/components/ui/Disclosure";
import ScoreDisplay from "@/components/ui/ScoreDisplay";
import PlaybookLink from "@/components/playbooks/PlaybookLink";
import VpsCategoryExplainer from "@/components/learn/VpsCategoryExplainer";
import { getPlaybookForVpsCategory } from "@/lib/playbooks/resourceMap";

import type { PathToStrongerItem, VPSResult } from "@/types";

function getCategoryBarColor(score: number | null): string {
  if (score === null) {
    return "bg-surface-muted";
  }
  if (score >= 7) {
    return "bg-success";
  }
  if (score >= 5) {
    return "bg-primary";
  }
  return "bg-warning";
}

type VPSResultPanelProps = {
  result: VPSResult;
  title?: string;
};

// Phase 10.6 -- Idea Lab V2, Part 5/6/9/10. Same data this panel always
// rendered (VPSResult is completely unchanged) -- reorganized around
// Design System V2's ScoreDisplay and "we don't know this yet" framing
// for Unavailable categories instead of a bare em dash.
//
// Phase 10.7, Part 16: NextMoves moved OUT of this panel to its own
// top-level section in VentureWorkspace (Overview -> Journey -> Modeled
// VPS -> Next 3 Moves -> Missions -> What If? -> Full Model) -- Next
// Moves now needs to pass a "Make this a mission" callback down, which a
// score-display panel has no business owning. VPSResultPanel itself
// still only ever renders the VPSResult its caller gives it; nothing
// about that contract changed.
export default function VPSResultPanel({ result, title = "Venture Potential Score" }: VPSResultPanelProps) {
  if (result.vps === null) {
    return (
      <BaseCard className="p-6 text-center">
        <p className="text-base font-semibold text-text-primary">
          Not enough assumptions yet to model a score.
        </p>
        <p className="mt-2 text-base leading-7 text-text-secondary">
          Add a few assumptions below — even a market size guess or a
          problem statement — to see an initial Venture Potential Score.
        </p>
      </BaseCard>
    );
  }

  return (
    <div className="space-y-6">
      <BaseCard className="p-6">
        <ScoreDisplay
          label={title}
          score={result.vps}
          scoreSuffix="/ 10"
          modeled
        />

        <div className="mx-auto mt-4 max-w-md">
          <Disclosure summary="What does this score mean?">
            {/* Phase 29B, Part 7: bumped from text-xs -- this is the core
                explanation of what the founder's score means, standing on
                its own with room to breathe (not a compact card), so it
                belongs with "important supporting copy" rather than
                tertiary metadata. */}
            <ul className="space-y-1.5 text-base leading-7 text-text-secondary">
              {/* Phase 14 -- Founder Journey Audit, Part 8/10: rewritten
                  without bare "VPS"/"SPS" acronyms. Neither term is
                  defined anywhere else in the modeled-venture founder
                  journey (the score is always labeled "Venture Potential
                  Score" in the UI around it), and "SPS" specifically
                  belongs to a completely different product surface (real,
                  evidence-analyzed startups) a first-time founder here has
                  no reason to have encountered yet. Same substantive
                  distinction, plain language. */}
              <li>• This score is <strong>modeled</strong> from your own assumptions — it&rsquo;s different from a real company&rsquo;s evidence-based VentureGPS Score, and the two are never comparable.</li>
              <li>• It reflects your own stated assumptions, not verified company performance.</li>
              <li>• Missing categories are expected for an early idea — that&rsquo;s honest, not a penalty.</li>
              <li>• Validation improves as you add real observations (interviews, signups, paying customers) — not by changing assumptions alone.</li>
            </ul>
          </Disclosure>
        </div>

        {/* Phase 29A, Part 13: restrained, targeted explanation for the
            one case this phase's audit actually found confusing --
            exactly one modeled category scored, with no independent
            validation evidence, so the overall score below sits at the
            neutral starting point rather than matching that one
            category's own displayed score further down. Shown only when
            compute_vps() itself reports this (sole_uncorroborated_category)
            -- never a general "what's affecting this score" dump of the
            internal model, and never shown when it doesn't apply. */}
        {result.sole_uncorroborated_category ? (
          <p className="mx-auto mt-3 max-w-md text-center text-base leading-7 text-text-secondary">
            Only one part of your model is scored so far, and nothing here has been
            independently validated yet — so this score reflects that it&rsquo;s a single,
            uncorroborated assumption, not the category score shown below. A second
            modeled category or real evidence (interviews, signups, paying customers)
            will let it reflect what you&rsquo;ve actually described.
          </p>
        ) : null}
      </BaseCard>

      {/* Phase 31C -- Founder Experience Simplification, Part 4/9: VPS is
          a diagnostic, not the report the workspace opens with -- the
          headline score + "what does this mean" above stays visible, but
          the full category-by-category breakdown, strengths/unknowns,
          and Path to Stronger are detail a founder can open when they
          actually want it, not content that competes with the one
          dominant next-action card above this panel. Nothing here is
          removed -- same data, same components, only collapsed by
          default (Disclosure, not a route or a second fetch). */}
      <Disclosure summary="See the full score breakdown" defaultOpen={false}>
        <div className="space-y-6 pt-2">
          <PathToStronger items={result.path_to_stronger} />

          <div>
            <h3 className="text-base font-semibold uppercase tracking-wide text-text-secondary">
              How your model breaks down
            </h3>

            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {result.categories.map((category) => {
                // Phase 10.9 -- Founder Playbooks V1, Part 5B: a single central
                // lookup (dashboard/lib/playbooks/resourceMap.ts) -- no new VPS
                // logic, compute_vps() untouched, category.key is the exact
                // same field this panel already renders.
                const playbook = getPlaybookForVpsCategory(category.key);

                return (
                  <BaseCard key={category.key} className="p-4">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium text-text-secondary">{category.label}</p>
                      <p className="text-sm font-semibold text-text-primary">
                        {category.score !== null ? category.score.toFixed(1) : "—"}
                      </p>
                    </div>

                    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-muted">
                      {category.score !== null ? (
                        <div
                          className={`h-full rounded-full ${getCategoryBarColor(category.score)}`}
                          style={{ width: `${Math.max(0, Math.min(100, (category.score / 10) * 100))}%` }}
                        />
                      ) : null}
                    </div>

                    {category.score === null ? (
                      <p className="mt-1.5 text-sm text-text-secondary">We don&rsquo;t know this yet</p>
                    ) : category.basis.length > 0 ? (
                      <p className="mt-1.5 text-base leading-7 text-text-secondary">{category.basis[0]}</p>
                    ) : null}

                    {/* Learn V1, Part 5/6: WHAT this category means and WHY it
                        matters, distinct from the Playbook link right below it
                        (HOW to actually work on it -- Part 12). */}
                    <VpsCategoryExplainer categoryKey={category.key} score={category.score} />

                    {playbook ? <PlaybookLink slug={playbook.slug} className="mt-2 block" /> : null}
                  </BaseCard>
                );
              })}
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <GuidanceList title="Strongest modeled areas" items={result.strengths} icon="▲" iconClass="text-success" />
            <GuidanceList title="Biggest modeled unknowns" items={result.risks} icon="▼" iconClass="text-danger" />
            <GuidanceList title="What you believe" items={result.key_assumptions} icon="•" iconClass="text-primary" />
            <DiscoveryGaps items={result.validation_gaps} />
          </div>
        </div>
      </Disclosure>
    </div>
  );
}

function GuidanceList({
  title,
  items,
  icon,
  iconClass,
}: {
  title: string;
  items: string[];
  icon: string;
  iconClass: string;
}) {
  if (items.length === 0) {
    return null;
  }

  return (
    <BaseCard className="p-4">
      <h3 className="text-base font-semibold text-text-primary">{title}</h3>
      <ul className="mt-2 space-y-1.5 text-base leading-6 text-text-secondary">
        {items.map((item, index) => (
          <li key={index} className="flex gap-2">
            <span aria-hidden="true" className={iconClass}>{icon}</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </BaseCard>
  );
}

// Founder Loop V2, Section 7 -- "Path to 8" investigation. Deliberately
// restrained: names WHICH currently-scored categories are below the
// modeled-strength threshold and WHY (the exact same `_STRENGTHEN_HINTS`
// text app/ai/vps_guidance.py's `_path_to_stronger()` already computed,
// ranked by weight x headroom), and explicitly disclaims a promised point
// gain -- Section 7's hard requirement not to fabricate an expected score
// delta. A founder who wants an actual number can already get one
// honestly through What If / Recalculate, which this section points to
// rather than duplicating.
function PathToStronger({ items }: { items: PathToStrongerItem[] }) {
  if (items.length === 0) {
    return null;
  }

  return (
    <BaseCard className="p-5">
      <h3 className="text-base font-semibold text-text-primary">Your shortest path to a stronger assessment</h3>
      <p className="mt-1 text-base leading-7 text-text-secondary">
        Your score changes only if the underlying venture fundamentals or evidence change — not by
        completing actions or reading playbooks. These are the categories most worth strengthening first.
      </p>

      <ul className="mt-3 space-y-3">
        {items.map((item) => (
          <li key={item.key} className="flex items-start justify-between gap-3 border-t border-border pt-3 first:border-t-0 first:pt-0">
            <div>
              <p className="text-base font-semibold text-text-primary">{item.label}</p>
              <p className="mt-0.5 text-sm text-text-secondary">{item.hint}</p>
            </div>
            <span className="shrink-0 text-base font-semibold text-text-muted">{item.score.toFixed(1)}</span>
          </li>
        ))}
      </ul>
    </BaseCard>
  );
}

// Phase 10.6, Part 6: missing information framed as discovery, not error --
// `validation_gaps` is unchanged from the backend (app/ai/vps_guidance.py
// already writes these as friendly, non-blaming sentences, e.g. "No
// customer interviews reported yet"). Renamed "Validation Gaps" ->
// "What you haven't learned yet" here, purely presentational.
function DiscoveryGaps({ items }: { items: string[] }) {
  if (items.length === 0) {
    return null;
  }

  // Phase 10.9, Part 5B: every validation_gaps line is, by construction
  // (see app/ai/vps_guidance.py::_validation_gaps()), about the same
  // "validation" VPS category -- one link for the whole section, not one
  // per line, matches Part 5's "do not plaster links everywhere."
  const playbook = getPlaybookForVpsCategory("validation");

  return (
    <BaseCard className="p-4">
      <h3 className="text-base font-semibold text-text-primary">What you haven&rsquo;t learned yet</h3>
      <ul className="mt-2 space-y-1.5 text-base leading-6 text-text-secondary">
        {items.map((item, index) => (
          <li key={index} className="flex gap-2">
            <span aria-hidden="true" className="text-warning">!</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
      {playbook ? <PlaybookLink slug={playbook.slug} label={`Learn how: ${playbook.title} →`} className="mt-2 block" /> : null}
    </BaseCard>
  );
}
