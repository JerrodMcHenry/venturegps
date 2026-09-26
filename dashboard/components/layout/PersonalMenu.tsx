"use client";

import { UserButton } from "@clerk/nextjs";

// Phase 10.3 -- Shell & Navigation Reset, Part 3. Restrained, consumer-
// facing personal navigation -- NOT the old 8-item sidebar recreated
// inside a dropdown. Route/backend concepts are completely unchanged --
// this is presentation language only:
//
//   My Ideas -> /idea-lab   (was "Idea Lab")
//   My Startup -> /founder  (was "Founder Workspace")
//
// Phase 15 -- Founder Beta Surface Audit, Part 11/15/21: "Watchlist"
// (/saved) and "Investor intelligence" (/investor) removed from this
// menu -- not deleted (Part 16). Both are watchlist/discovery surfaces
// over the SAME cold-start-affected canonical startup population
// PRIMARY_NAVIGATION's own "Explore" removal addresses (see
// TopNav.tsx) -- there is currently nothing meaningful for a founder to
// watch or for an investor to browse. Both routes remain fully
// functional at their existing URLs for any user who already knows to
// go there (auth/authorization completely unchanged); this is a
// visibility decision only. Revert alongside Explore once the dataset
// is credible.
//
// Shown unconditionally to every signed-in user, same as the old
// Sidebar's own behavior -- each destination's own page already handles
// "you have nothing here yet" honestly (FounderHome's existing empty
// state), so this menu doesn't need to fetch anything to decide what to
// show.
//
// Portfolio Release Task 4 -- Unified UX, Phase 2: "My Ideas" (/idea-lab),
// "My Startup" (/founder), and "Learn" (/playbooks) are BACK here. Phase 32
// (see this file's own history below) had promoted them out of this menu
// into TopNav.tsx's always-visible PRIMARY_NAVIGATION; this task's own
// explicit instruction is the opposite move -- the primary release
// journey's nav row is now Analyze / My Analyses / Saved, and "keep
// existing founder... routes intact but remove competing navigation from
// the primary release journey" is exactly this: same routes, same auth,
// demoted from a competing top-level nav item back to an account-menu
// destination, not deleted. Nothing about /idea-lab or /founder
// themselves changed.
//
// Phase 10.3 follow-up fix: this originally wrapped Clerk's own
// <UserButton /> (which renders its own <button>) inside a second,
// hand-rolled <button> used to open a custom popover -- invalid nested
// interactive markup that also silently ate every click before Clerk's
// own trigger ever saw it, so its native "Manage account" / "Sign out"
// dialog could never open. There was no way to sign out. Fixed by
// dropping the custom trigger/popover entirely and using Clerk's own
// supported extension point instead -- <UserButton.MenuItems> +
// <UserButton.Link> add these four destinations directly into Clerk's
// own account menu, alongside its built-in Manage account / Sign out
// actions, which is exactly what Part 3 asked for ("Use existing Clerk
// account functionality, not a custom auth system") and what "restrained,
// not another giant dropdown" means in practice: one native menu, not two
// stacked ones.
const ICON_CLASS = "size-4";

// Portfolio Release Task 4, Phase 2: reinstated alongside the menu links
// they illustrate (see this file's own comment above PersonalMenu()) --
// same icons Phase 32 removed, not redesigned.
function IdeaIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" className={ICON_CLASS}>
      <path d="M12 3l2.4 5.3 5.6.6-4.2 3.9 1.2 5.6L12 15.8l-5 2.6 1.2-5.6-4.2-3.9 5.6-.6L12 3z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
    </svg>
  );
}

function StartupIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" className={ICON_CLASS}>
      <path d="M12 3l2.4 5.3 5.6.6-4.2 3.9 1.2 5.6L12 15.8l-5 2.6 1.2-5.6-4.2-3.9 5.6-.6L12 3z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

function LearnIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" className={ICON_CLASS}>
      <path
        d="M4 5.5A2.5 2.5 0 0 1 6.5 3H12v16H6.5A2.5 2.5 0 0 0 4 21.5v-16z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path
        d="M20 5.5A2.5 2.5 0 0 0 17.5 3H12v16h5.5a2.5 2.5 0 0 1 2.5 2.5v-16z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function FeedbackIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" className={ICON_CLASS}>
      <path d="M21 15a2 2 0 0 1-2 2H8l-4 4V6a2 2 0 0 1 2-2h13a2 2 0 0 1 2 2v9Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
    </svg>
  );
}

// Phase 29 -- Private Beta Readiness, Part 22. No existing support/
// contact/feedback mechanism was found anywhere in this codebase
// (confirmed by direct grep before adding this). This is the smallest
// possible option on the directive's own preferred hierarchy: a plain
// `mailto:` link, reusing the founder's own already-installed mail
// client -- zero new backend endpoint, zero new persistence, zero new
// architecture. The prefilled subject/body asks exactly the three
// questions the directive names (confusing / broken / an idea) and
// nothing else; whatever the founder writes goes directly from their own
// mail client to the creator's inbox and is never seen by, or stored in,
// SIE itself.
const FEEDBACK_MAILTO =
  "mailto:jamcoderswe@gmail.com?subject=" +
  encodeURIComponent("SIE feedback") +
  "&body=" +
  encodeURIComponent(
    "Something confusing:\n\nSomething broken:\n\nAn idea:\n\n(Delete whichever don't apply -- anything at all is welcome.)"
  );

// Phase 10.9 -- Founder Playbooks V1, Part 11: no new TopNav item --
// "Learn" is discovered here, the same restrained account-menu path
// every other personal/non-primary destination already uses, plus
// contextual links from inside the product itself (see
// dashboard/lib/playbooks/resourceMap.ts's own callers). /playbooks
// itself is public (no auth), so this link works identically for every
// signed-in user regardless of what they've built so far.
// Phase 32 -- Product Information Architecture + Seamless User Journey,
// Part 2/9: "My Ideas," "My Startup," and "Learn" removed from this menu
// -- Section 9's own "duplicate destinations" failure mode, now that all
// three are always-visible primary nav items (TopNav.tsx/MobileTabBar.tsx)
// rather than buried inside the account dropdown. Nothing about the
// destinations themselves changed (same routes, same auth); this menu's
// only remaining job is genuinely account-scoped actions Clerk itself
// doesn't already provide a home for.
// Milestone 1, Task 1 -- Unify Navigation, correction: an "Evidence review" -> /admin/v2-review link was
// briefly added here, shown unconditionally to every signed-in user. That was wrong: this menu has no way to
// tell an admin from any other signed-in user before the click, so showing it to everyone advertised an
// admin-only tool to non-admins as if it were theirs to use. The fix is not to gate the link on some
// client-side admin check -- there is no trusted, server-verified admin capability exposed to the frontend to
// gate it on. ADMIN_USER_IDS is explicitly backend-only (app/auth.py: "Never exposed to the frontend... no
// endpoint returns its value") and no /me-style endpoint or Clerk claim mirrors it. Inferring admin status
// from anything the client already has (email address, Clerk publicMetadata, etc.) would duplicate the
// backend's own authorization rule in a second, unsynchronized place -- worse than not showing a link at all.
// Introducing a new backend endpoint just to answer "am I admin" is also out of scope for this task. So: no
// link here for now. Admins reach /admin/v2-review directly by URL, same as before this menu entry ever
// existed; the page's own auth.protect() (app/admin/v2-review/page.tsx) and the backend's RequireAdmin on
// every /admin/v2-review/* call (app/v2_review_api.py) are both completely unchanged and remain the only real
// boundary. Revisit once a trusted, server-verified "is this user an admin" signal actually exists.
export default function PersonalMenu() {
  return (
    <UserButton appearance={{ elements: { userButtonAvatarBox: "size-9" } }}>
      <UserButton.MenuItems>
        <UserButton.Link label="My Ideas" href="/idea-lab" labelIcon={<IdeaIcon />} />
        <UserButton.Link label="My Startup" href="/founder" labelIcon={<StartupIcon />} />
        <UserButton.Link label="Learn" href="/playbooks" labelIcon={<LearnIcon />} />
        <UserButton.Link label="Send feedback" href={FEEDBACK_MAILTO} labelIcon={<FeedbackIcon />} />
      </UserButton.MenuItems>
    </UserButton>
  );
}
