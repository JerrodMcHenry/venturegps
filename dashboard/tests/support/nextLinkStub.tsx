// Test-only stub for next/link, used solely by tests/support/tsxLoader.mjs to let Section B's real component
// tree render outside the Next.js App Router runtime (which next/link's real implementation needs a router
// context for). Renders a plain <a>; the interaction tests here never click these links, only the market
// selection controls, so this only needs to exist and carry its href/children through.
import * as React from "react";

type StubLinkProps = React.PropsWithChildren<{
  href: string;
  className?: string;
}>;

export default function StubLink({ href, className, children }: StubLinkProps) {
  return React.createElement("a", { href, className }, children);
}
