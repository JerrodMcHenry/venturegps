"use client";

import { useState } from "react";

import PageHeader from "@/components/layout/PageHeader";
import Badge from "@/components/ui/Badge";
import BaseCard from "@/components/ui/BaseCard";
import Button from "@/components/ui/Button";
import Disclosure from "@/components/ui/Disclosure";
import EmptyState from "@/components/ui/EmptyState";
import ErrorMessage from "@/components/ui/ErrorMessage";
import Input from "@/components/ui/Input";
import Progress from "@/components/ui/Progress";
import ScoreDisplay from "@/components/ui/ScoreDisplay";
import Skeleton, { SkeletonLines } from "@/components/ui/Skeleton";
import Textarea from "@/components/ui/Textarea";
import ThemeToggle from "@/components/ui/ThemeToggle";

// Design System V2 (Phase 10.4), Part 11. Section-by-section gallery of
// every primitive this phase introduced or migrated, in representative
// states -- the practical verification surface for Part 14's light/dark
// and desktop/mobile checks. Not linked from anywhere in the app chrome
// (see page.tsx's own comment for why it's still safe as a public route).
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-4 border-t border-border pt-8 first:border-t-0 first:pt-0">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-text-muted">{title}</h2>
      {children}
    </section>
  );
}

export default function DesignSystemShowcase() {
  const [loadingDemo, setLoadingDemo] = useState(false);

  return (
    <>
      <PageHeader
        title="Design System V2"
        subtitle="Dev-only component gallery -- not a production page. 404s outside next dev."
        action={<ThemeToggle />}
      />

      <div className="space-y-10">
        <Section title="Typography">
          <div className="space-y-2">
            <p className="text-5xl font-bold tracking-tight text-text-primary">Display / hero</p>
            <p className="text-4xl font-bold tracking-tight text-text-primary">Page title</p>
            <p className="text-xl font-semibold text-text-primary">Section title</p>
            <p className="text-base font-semibold text-text-primary">Card / item title</p>
            <p className="text-sm text-text-primary">Body text -- the default reading size for most copy.</p>
            <p className="text-sm text-text-secondary">Supporting body -- secondary explanatory text.</p>
            <p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">Label</p>
            <p className="text-xs text-text-muted">Metadata -- timestamps, counts, fine print.</p>
          </div>
        </Section>

        <Section title="Buttons">
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="primary">Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="subtle">Subtle</Button>
            <Button variant="destructive">Destructive</Button>
            <Button variant="primary" loading={loadingDemo} onClick={() => setLoadingDemo((v) => !v)}>
              {loadingDemo ? "Loading" : "Toggle loading"}
            </Button>
            <Button variant="primary" disabled>
              Disabled
            </Button>
            <Button variant="secondary" size="sm">
              Small
            </Button>
            <Button variant="secondary" size="lg">
              Large
            </Button>
          </div>
        </Section>

        <Section title="Inputs">
          <div className="grid gap-6 sm:grid-cols-2">
            <Input id="showcase-input" label="Company website" placeholder="https://example.com" />
            <Input id="showcase-input-error" label="Company website" defaultValue="not-a-url" error="Website URL must start with http:// or https://" />
          </div>
          <Textarea
            id="showcase-textarea"
            label="Additional information"
            placeholder="Large, comfortable textarea for longer input..."
            help="Optional -- supplements whatever else you provide."
          />
        </Section>

        <Section title="Surfaces / cards">
          <div className="grid gap-4 sm:grid-cols-3">
            <BaseCard className="p-5">
              <p className="text-sm font-semibold text-text-primary">Default</p>
              <p className="mt-1 text-xs text-text-muted">Normal content surface.</p>
            </BaseCard>
            <BaseCard variant="raised" className="p-5">
              <p className="text-sm font-semibold text-text-primary">Raised</p>
              <p className="mt-1 text-xs text-text-muted">Elevated / interactive surface.</p>
            </BaseCard>
            <BaseCard variant="subtle" className="p-5">
              <p className="text-sm font-semibold text-text-primary">Subtle</p>
              <p className="mt-1 text-xs text-text-muted">Quiet grouped surface.</p>
            </BaseCard>
          </div>
        </Section>

        <Section title="Badges">
          <div className="flex flex-wrap gap-2">
            <Badge tone="neutral">Neutral</Badge>
            <Badge tone="primary">Primary</Badge>
            <Badge tone="success">Success</Badge>
            <Badge tone="warning">Warning</Badge>
            <Badge tone="danger">Danger</Badge>
            <Badge tone="info">Info</Badge>
            <Badge tone="confidence-high">High confidence</Badge>
            <Badge tone="confidence-medium">Medium confidence</Badge>
            <Badge tone="confidence-low">Low confidence</Badge>
          </div>
        </Section>

        <Section title="Progress">
          <div className="max-w-sm space-y-6">
            <Progress value={68} label="Venture model completeness" valueLabel="68%" tone="primary" />
            <Progress value={3} max={5} label="Assumptions validated" valueLabel="3 of 5" tone="success" />
            <Progress value={40} label="Fundraising readiness" valueLabel="Developing" tone="warning" />
          </div>
        </Section>

        <Section title="Score presentation">
          <div className="grid gap-4 sm:grid-cols-3">
            <BaseCard className="p-6">
              <ScoreDisplay
                label="VentureGPS Score"
                score={78.8}
                statusLabel="Promising but Needs Diligence"
                statusTone="primary"
                delta={{ value: 1.8, direction: "negative" }}
              />
            </BaseCard>
            <BaseCard className="p-6">
              <ScoreDisplay
                label="Venture Potential Score"
                score={5.2}
                scoreSuffix="/ 10"
                statusLabel="Modeled / assumption-based"
                statusTone="warning"
                modeled
              />
            </BaseCard>
            <BaseCard className="p-6">
              <ScoreDisplay label="Fundraising Readiness" score={null} unavailableText="Not enough information yet." />
            </BaseCard>
          </div>
        </Section>

        <Section title="Empty state">
          <EmptyState
            title="No ventures yet"
            description="Model your first startup idea to see a Venture Potential Score."
            action={<Button variant="primary">Model a new venture</Button>}
          />
        </Section>

        <Section title="Loading state">
          <div className="grid gap-4 sm:grid-cols-2">
            <Skeleton className="h-24 w-full" />
            <BaseCard className="p-5">
              <SkeletonLines count={3} />
            </BaseCard>
          </div>
        </Section>

        <Section title="Error state">
          <ErrorMessage>Something went wrong. Your input hasn&rsquo;t been lost -- you can try again.</ErrorMessage>
        </Section>

        <Section title="Disclosure">
          <Disclosure summary="What does this score mean?">
            <p className="text-sm text-text-secondary">
              Progressive disclosure: headline insight first, deeper detail only once the reader
              chooses to expand it.
            </p>
          </Disclosure>
        </Section>
      </div>
    </>
  );
}
