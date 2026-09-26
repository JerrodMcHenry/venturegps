type PageHeaderProps = {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  // Task 5 -- Unified Visual Design: opt-in only. "default" is the exact,
  // unchanged className this component always returned -- every one of
  // this component's ~15 existing call sites passes no `variant` at all,
  // so they render byte-identically. "glow" is scoped to exactly the
  // four routes that task named (Analyze, My Analyses, Saved, the
  // startup report): a gradient-text title inside a restrained glass
  // band, echoing the homepage hero's own glass-panel treatment, without
  // touching a single page this task didn't ask for.
  variant?: "default" | "glow";
};

// Phase 10.3: switched from hardcoded slate-* colors (which only ever
// looked correct in dark mode -- text-white on a light background is
// invisible) to the same design tokens every other component in this
// codebase already uses. Pure color-token fix, no layout/behavior
// change -- this component is used on nearly every page (15 call sites),
// so it's directly in-path for the shell's own light/dark verification.
//
// Design System V2 (Phase 10.4), Part 4/12: page title bumped one step
// larger (3xl/4xl, was 2xl/3xl) -- Part 4's "large moments should be
// allowed to feel large" applied to the one heading every single page in
// the app renders. Nothing else about this component changed; it's still
// pure layout chrome with zero page-specific content.
export default function PageHeader({
  title,
  subtitle,
  action,
  variant = "default",
}: PageHeaderProps) {
  const isGlow = variant === "glow";

  return (
    <header
      className={[
        "mb-8 flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between",
        isGlow
          ? "rounded-2xl border border-primary/15 bg-surface/70 p-6 shadow-lg shadow-primary/5 backdrop-blur-xl supports-[backdrop-filter]:bg-surface/60 sm:p-8"
          : "border-b border-border pb-7",
      ].join(" ")}
    >
      <div className="min-w-0">
        <h1
          className={[
            "text-3xl font-bold tracking-tight sm:text-4xl",
            isGlow
              ? "bg-gradient-to-r from-accent via-primary to-secondary bg-clip-text text-transparent"
              : "text-text-primary",
          ].join(" ")}
        >
          {title}
        </h1>

        {/* Phase 31C-C -- Global Visual Scale + Readability Correction,
            Part 1/9: this subtitle is the one-line description of what
            the entire page is for, on essentially every page in the app
            -- real explanatory copy, not secondary text. Bumped to a
            flat 16px (was 14px on mobile, 16px only from sm+) and a
            slightly wider reading column. */}
        {subtitle ? (
          <p className="mt-2 max-w-3xl text-base leading-7 text-text-secondary">
            {subtitle}
          </p>
        ) : null}
      </div>

      {action ? (
        <div className="flex shrink-0 items-center">{action}</div>
      ) : null}
    </header>
  );
}
