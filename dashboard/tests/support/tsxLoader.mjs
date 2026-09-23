// Node module customization hooks (registered via node:module's `register()`) that let a plain `node` process
// import the REAL .tsx component files under test -- Node's own built-in TypeScript support strips *types* but
// does not implement a JSX transform, so a bare `node` process cannot load a .tsx file at all (confirmed
// directly: "Unknown file extension .tsx"). This uses the `typescript` package already in package.json's
// devDependencies (no new transform dependency) to transpile .tsx/.ts source on the fly, and redirects
// `next/image`/`next/link` to the local stubs in tests/support/ so the component tree can render without the
// full Next.js app runtime those two specifically require. Everything else -- the actual Section B components,
// interactionLogic.ts, sectionBMarkets.ts, signalLabels.ts, DirectionBadge.tsx, IllustrativeTag.tsx -- loads and
// runs unmodified.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const REDIRECTS = {
  "next/image": new URL("./nextImageStub.tsx", import.meta.url).href,
  "next/link": new URL("./nextLinkStub.tsx", import.meta.url).href,
};

// dashboard/tsconfig.json maps "@/*" to "./*" (the dashboard root) for the bundler; Node's own resolver knows
// nothing about tsconfig path aliases, so value imports through "@/..." fail under plain `node` (this is the
// same limitation noted in sectionBMarkets.ts's own relative-import workaround). The dashboard root is this
// file's own directory's grandparent (tests/support/ -> tests/ -> dashboard/).
const DASHBOARD_ROOT = new URL("../../", import.meta.url);

const EXTENSION_CANDIDATES = ["", ".tsx", ".ts", "/index.tsx", "/index.ts"];

export async function resolve(specifier, context, nextResolve) {
  if (Object.prototype.hasOwnProperty.call(REDIRECTS, specifier)) {
    return { url: REDIRECTS[specifier], shortCircuit: true };
  }

  const target = specifier.startsWith("@/") ? new URL(specifier.slice(2), DASHBOARD_ROOT).href : specifier;
  const isLocalSpecifier = specifier.startsWith("@/") || specifier.startsWith(".") || specifier.startsWith("/");

  if (!isLocalSpecifier) {
    return nextResolve(specifier, context);
  }

  // Component/module imports in this codebase are written without an extension (bundler-resolved); Node's ESM
  // resolver needs one. Try the bare specifier first (covers imports that already spell out ".tsx"/".ts"), then
  // each real extension in turn.
  let lastError;
  for (const suffix of EXTENSION_CANDIDATES) {
    try {
      return await nextResolve(target + suffix, context);
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}

export async function load(url, context, nextLoad) {
  if (url.endsWith(".tsx") || url.endsWith(".ts")) {
    const filePath = fileURLToPath(url);
    const source = readFileSync(filePath, "utf8");
    const output = ts.transpileModule(source, {
      compilerOptions: {
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2022,
        jsx: ts.JsxEmit.ReactJSX,
        esModuleInterop: true,
        verbatimModuleSyntax: false,
      },
      fileName: filePath,
    });
    return { format: "module", source: output.outputText, shortCircuit: true };
  }
  return nextLoad(url, context);
}
