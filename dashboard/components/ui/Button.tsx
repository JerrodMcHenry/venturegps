import type { ButtonHTMLAttributes, ReactNode } from "react";

// Design System V2 (Phase 10.4), Part 6. No shared Button existed before
// this -- 23 files across dashboard/ each hand-rolled their own <button>
// styling (see AnalyzeStartupForm.tsx for a typical example), which is
// exactly the "duplicate visual patterns" Part 1 asks this phase to find
// and consolidate. This covers the variants/states that repo actually
// uses today; it does not invent speculative ones.
// Task 5 -- Unified Visual Design: "gradient" added -- the cyan-to-violet
// gradient CTA treatment the homepage hero and PublicNav's "Get Started"
// already use (`from-accent to-secondary`), now a real Button variant
// instead of each of those hand-rolling the same gradient classes.
// Reserved for the ONE most prominent call-to-action per page (the
// homepage's "Analyze a startup", Analyze's own submit) -- not a
// replacement for "primary" everywhere, which would dilute exactly the
// "one prominent CTA" emphasis this task asks for.
export type ButtonVariant = "primary" | "secondary" | "subtle" | "destructive" | "gradient";
export type ButtonSize = "sm" | "md" | "lg";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: ReactNode;
  children?: ReactNode;
};

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary:
    "bg-primary text-white hover:bg-primary-hover disabled:hover:bg-primary",
  secondary:
    "border border-border bg-surface text-text-primary hover:border-primary/40 hover:bg-surface-muted",
  subtle:
    "text-text-secondary hover:bg-surface-muted hover:text-text-primary",
  destructive:
    "bg-danger text-white hover:bg-danger/90 disabled:hover:bg-danger",
  gradient:
    "bg-gradient-to-r from-accent to-secondary text-white shadow-lg shadow-primary/30 hover:opacity-90 disabled:hover:opacity-100",
};

// min-h-11 (44px) on every size -- Part 10's mobile touch-target floor --
// sm only shrinks horizontal padding/font, never the tap height.
//
// Phase 31C-C -- Global Visual Scale + Readability Correction, Part 9:
// every size bumped one step (sm: 12px->14px, md: 14px->16px) -- `md` is
// the default used by nearly every primary CTA in the app ("Build My
// Startup", "Start this action", "Save Changes"), so it was rendering
// the app's most important click targets at only 14px. `sm` (used for
// real secondary actions like "Add to Plan", not decoration) is raised
// off the 12px floor Part 1 treats as exceptional-only.
const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: "min-h-11 px-3.5 text-sm sm:min-h-9",
  md: "min-h-11 px-5 text-base",
  lg: "min-h-12 px-7 text-lg",
};

function Spinner() {
  return (
    <span
      aria-hidden="true"
      className="size-4 shrink-0 animate-spin rounded-full border-2 border-current/30 border-t-current"
    />
  );
}

export default function Button({
  variant = "primary",
  size = "md",
  loading = false,
  icon,
  disabled,
  className = "",
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={[
        "inline-flex items-center justify-center gap-2 rounded-xl font-semibold",
        "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        "disabled:cursor-not-allowed disabled:opacity-50",
        VARIANT_CLASSES[variant],
        SIZE_CLASSES[size],
        className,
      ].join(" ")}
      {...props}
    >
      {loading ? <Spinner /> : icon ?? null}
      {children}
    </button>
  );
}
