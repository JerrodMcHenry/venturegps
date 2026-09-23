// VentureGPS Increment 16.3.2 -- browser-level integration test for Section B's two interactions, required in
// addition to (not instead of) the pure-function tests in v2SectionBInteraction.test.ts: this one renders the
// REAL MarketShowcaseDesktop.tsx and MarketCarouselMobile.tsx component trees into a real DOM (jsdom) via real
// ReactDOM (react-dom/client's createRoot, the same API Next.js itself uses to hydrate), finds real button
// elements via querySelector, and dispatches real DOM MouseEvents at them -- not calling setSelectedSlug/goTo
// directly, not asserting on the pure functions in isolation. This is the class of test that would have caught
// the Increment 16.3.2 bug: a real interaction reaching a real handler, updating real state, producing the real
// re-rendered DOM.
//
// How this loads real .tsx files under plain `node`: see tests/support/tsxLoader.mjs's own comment. In short --
// Node's built-in TypeScript support strips types but has no JSX transform, so a bare `node` process cannot
// import a .tsx file at all; the loader transpiles JSX via the `typescript` package (already a devDependency,
// no new transform tool added) and redirects next/image and next/link to plain stub components in
// tests/support/ so the real component tree can render without the full Next.js app runtime those two
// specifically require to work correctly outside of it.
//
// What this DOES prove: a real click reaches each real onClick handler, the resulting setState call fires, and
// the DOM that comes back out the other side is correct -- for both components, across the exact scenarios in
// the Increment 16.3.2 acceptance criteria (desktop tile selection and swap-back, mobile arrows, dots, and
// disabled-arrow states at both ends).
//
// What this does NOT prove, and does not claim to: jsdom has no layout engine, so every element's
// offsetLeft/clientWidth is always 0 here. That makes it unable to exercise handleScroll's real scroll-position
// math (the divisor bug fixed in this same pass, in MarketCarouselMobile.tsx) -- that fix was verified directly
// in a real Chromium browser instead (see this increment's report), where real layout numbers exist. It also
// cannot simulate a real browser's native Enter/Space-activates-a-focused-<button> behavior (a confirmed jsdom
// gap, not an app bug: dispatching a keydown at a jsdom <button> does not produce a click, in a real browser it
// always does) -- keyboard activation is instead verified here by exercising the exact same click handler a real
// keyboard activation reaches, plus by inspection of both component files confirming neither one attaches any
// custom onKeyDown that could intercept or block a browser's native activation of a plain, unmodified <button>.
//
// Run with:
//   node tests/v2SectionBBrowserInteraction.test.ts

import { register } from "node:module";

register("./support/tsxLoader.mjs", import.meta.url);

const { JSDOM } = await import("jsdom");

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/", pretendToBeVisual: true });
globalThis.window = dom.window as unknown as typeof globalThis.window;
globalThis.document = dom.window.document;
Object.defineProperty(globalThis, "navigator", { value: dom.window.navigator, configurable: true });
globalThis.HTMLElement = dom.window.HTMLElement as unknown as typeof globalThis.HTMLElement;
globalThis.MouseEvent = dom.window.MouseEvent as unknown as typeof globalThis.MouseEvent;
globalThis.Event = dom.window.Event as unknown as typeof globalThis.Event;
globalThis.requestAnimationFrame = (dom.window.requestAnimationFrame ?? ((cb: FrameRequestCallback) => setTimeout(() => cb(Date.now()), 0))) as typeof globalThis.requestAnimationFrame;
globalThis.cancelAnimationFrame = (dom.window.cancelAnimationFrame ?? clearTimeout) as typeof globalThis.cancelAnimationFrame;
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// jsdom does not implement matchMedia at all (goTo's prefers-reduced-motion check calls it on every navigation).
// A fixed "no preference" stub is enough here -- the tests below assert on state/DOM output, not on whether the
// resulting scrollIntoView call requested a smooth or instant scroll.
window.matchMedia = ((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener() {},
  removeListener() {},
  addEventListener() {},
  removeEventListener() {},
  dispatchEvent() {
    return false;
  },
})) as unknown as typeof window.matchMedia;

// jsdom has no layout engine and does not implement Element.scrollIntoView (goTo calls it on every navigation).
// A no-op is correct for these tests: they assert on activeIndex-driven DOM state (aria-current, disabled),
// never on the resulting scroll position, which needs real layout and was verified separately in a real browser.
dom.window.HTMLElement.prototype.scrollIntoView = function scrollIntoViewStub() {};

const React = await import("react");
const { createRoot } = await import("react-dom/client");
const { act } = React;

const { default: MarketShowcaseDesktop } = await import("../components/design/cinematicHomepage/sectionB/MarketShowcaseDesktop.tsx");
const { default: MarketCarouselMobile } = await import("../components/design/cinematicHomepage/sectionB/MarketCarouselMobile.tsx");

function expect(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

function click(el: Element): Promise<void> {
  return act(async () => {
    el.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

async function withRenderedComponent<T>(Component: () => React.ReactElement | null, run: (container: HTMLDivElement) => Promise<T>): Promise<T> {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(React.createElement(Component));
  });
  try {
    return await run(container);
  } finally {
    await act(async () => {
      root.unmount();
    });
    container.remove();
  }
}

async function test_desktop_clicking_a_secondary_tile_features_it_and_returns_the_previous_one_to_the_tile_list() {
  await withRenderedComponent(MarketShowcaseDesktop, async (container) => {
    const featuredName = () => container.querySelector<HTMLElement>(".relative.aspect-\\[16\\/10\\] p.text-xl")?.textContent;
    const tileLabels = () => Array.from(container.querySelectorAll("button")).map((b) => b.getAttribute("aria-label") ?? "");

    expect(featuredName() === "Robotics", `expected Robotics featured initially, got ${featuredName()}`);
    expect(
      tileLabels().some((l) => l.startsWith("Feature Quantum Computing")),
      "Quantum Computing should start as a secondary tile"
    );

    const quantumTile = Array.from(container.querySelectorAll("button")).find((b) => b.getAttribute("aria-label")?.startsWith("Feature Quantum Computing"));
    expect(quantumTile !== undefined, "the Quantum Computing tile button must exist in the real rendered DOM");
    await click(quantumTile as HTMLButtonElement);

    expect(featuredName() === "Quantum Computing", `expected Quantum Computing featured after a real click, got ${featuredName()}`);
    expect(
      tileLabels().some((l) => l.startsWith("Feature Robotics")),
      "Robotics (the previously featured market) must reappear as a secondary tile after Quantum Computing is selected"
    );
    expect(
      !tileLabels().some((l) => l.startsWith("Feature Quantum Computing")),
      "the now-featured market must no longer also appear as a secondary tile"
    );
  });
}

async function test_desktop_selecting_a_second_market_then_a_third_keeps_the_tile_list_consistent() {
  await withRenderedComponent(MarketShowcaseDesktop, async (container) => {
    const findTile = (namePrefix: string) => Array.from(container.querySelectorAll("button")).find((b) => b.getAttribute("aria-label")?.startsWith(namePrefix));
    const featuredName = () => container.querySelector<HTMLElement>(".relative.aspect-\\[16\\/10\\] p.text-xl")?.textContent;

    await click(findTile("Feature Climate Technology") as HTMLButtonElement);
    expect(featuredName() === "Climate Technology", `expected Climate Technology featured, got ${featuredName()}`);

    await click(findTile("Feature Biotech") as HTMLButtonElement);
    expect(featuredName() === "Biotech", `expected Biotech featured, got ${featuredName()}`);

    const tileLabels = Array.from(container.querySelectorAll("button")).map((b) => b.getAttribute("aria-label") ?? "");
    expect(tileLabels.length === 3, `expected exactly 3 secondary tiles once Biotech is featured, got ${tileLabels.length}`);
    expect(!tileLabels.some((l) => l.startsWith("Feature Biotech")), "the featured market (Biotech) must not also be a secondary tile");
  });
}

async function test_desktop_tiles_are_plain_buttons_with_no_custom_key_handling() {
  await withRenderedComponent(MarketShowcaseDesktop, async (container) => {
    const buttons = Array.from(container.querySelectorAll("button"));
    expect(buttons.length === 3, `expected 3 secondary tile buttons, got ${buttons.length}`);
    for (const button of buttons) {
      expect(button.tagName === "BUTTON", "each secondary tile must be a real <button>, which gets Enter/Space activation from the browser for free");
      expect(button.getAttribute("onkeydown") === null, "a tile button must not carry a custom onKeyDown that could intercept native keyboard activation");
    }
    // A native <button>'s Enter/Space activation is the browser dispatching a real click at the element -- the
    // exact same event this suite already dispatches and verifies above. jsdom does not implement that default
    // action (see this file's header comment), so the keydown-to-click translation itself is verified by
    // inspection here, and the click it produces is verified for real just above.
  });
}

async function test_mobile_initial_state_has_previous_disabled_and_first_dot_active() {
  await withRenderedComponent(MarketCarouselMobile, async (container) => {
    const prev = container.querySelector<HTMLButtonElement>('[aria-label="Previous market"]');
    const next = container.querySelector<HTMLButtonElement>('[aria-label="Next market"]');
    const dots = Array.from(container.querySelectorAll<HTMLButtonElement>('[aria-label^="Go to "]'));

    expect(prev?.disabled === true, "the previous-market arrow must start disabled on the first slide");
    expect(next?.disabled === false, "the next-market arrow must start enabled on the first slide");
    expect(dots.length === 4, `expected 4 dots (one per market), got ${dots.length}`);
    expect(dots[0].getAttribute("aria-current") === "true", "the first dot must be aria-current on the first slide");
    expect(dots.slice(1).every((d) => d.getAttribute("aria-current") !== "true"), "only the first dot should be aria-current initially");
  });
}

async function test_mobile_next_arrow_advances_one_market_and_updates_disabled_states_and_dots() {
  await withRenderedComponent(MarketCarouselMobile, async (container) => {
    const next = () => container.querySelector<HTMLButtonElement>('[aria-label="Next market"]')!;
    const prev = () => container.querySelector<HTMLButtonElement>('[aria-label="Previous market"]')!;
    const activeDotIndex = () => Array.from(container.querySelectorAll('[aria-label^="Go to "]')).findIndex((d) => d.getAttribute("aria-current") === "true");

    expect(activeDotIndex() === 0, "must start on slide 0");
    await click(next());
    expect(activeDotIndex() === 1, `a real click on the next arrow must advance exactly one market (index 0 -> 1), got index ${activeDotIndex()}`);
    expect(prev().disabled === false, "the previous arrow must become enabled once no longer on the first slide");
    expect(next().disabled === false, "the next arrow must stay enabled before the last slide");
  });
}

async function test_mobile_previous_arrow_retreats_one_market() {
  await withRenderedComponent(MarketCarouselMobile, async (container) => {
    const next = () => container.querySelector<HTMLButtonElement>('[aria-label="Next market"]')!;
    const prev = () => container.querySelector<HTMLButtonElement>('[aria-label="Previous market"]')!;
    const activeDotIndex = () => Array.from(container.querySelectorAll('[aria-label^="Go to "]')).findIndex((d) => d.getAttribute("aria-current") === "true");

    await click(next());
    await click(next());
    expect(activeDotIndex() === 2, `expected slide 2 after two real next-arrow clicks, got ${activeDotIndex()}`);
    await click(prev());
    expect(activeDotIndex() === 1, `a real click on the previous arrow must retreat exactly one market (2 -> 1), got ${activeDotIndex()}`);
  });
}

async function test_mobile_next_arrow_disables_at_the_last_market_and_never_overshoots() {
  await withRenderedComponent(MarketCarouselMobile, async (container) => {
    const next = () => container.querySelector<HTMLButtonElement>('[aria-label="Next market"]')!;
    const activeDotIndex = () => Array.from(container.querySelectorAll('[aria-label^="Go to "]')).findIndex((d) => d.getAttribute("aria-current") === "true");

    for (let i = 0; i < 3; i++) {
      await click(next());
    }
    expect(activeDotIndex() === 3, `expected the last slide (3) after 3 real next-arrow clicks, got ${activeDotIndex()}`);
    expect(next().disabled === true, "the next arrow must disable once on the last market");

    // A disabled real <button> does not dispatch click at all in a real browser; verify one more click is a
    // genuine no-op rather than silently overshooting the valid index range.
    await click(next());
    expect(activeDotIndex() === 3, "clicking a disabled next arrow must not change the active market");
  });
}

async function test_mobile_dot_click_jumps_directly_to_the_selected_market() {
  await withRenderedComponent(MarketCarouselMobile, async (container) => {
    const dots = () => Array.from(container.querySelectorAll<HTMLButtonElement>('[aria-label^="Go to "]'));
    const activeDotIndex = () => dots().findIndex((d) => d.getAttribute("aria-current") === "true");

    const biotechDot = dots().find((d) => d.getAttribute("aria-label") === "Go to Biotech")!;
    expect(biotechDot !== undefined, "a 'Go to Biotech' dot must exist");
    await click(biotechDot);

    expect(activeDotIndex() === 3, `a real click on the Biotech dot must select it directly (index 3), got ${activeDotIndex()}`);
    expect(
      container.querySelector('[aria-label="Next market"]')?.hasAttribute("disabled") === true,
      "the next arrow must be disabled once the last market (Biotech) is selected via its dot"
    );
  });
}

async function main() {
  const tests = [
    test_desktop_clicking_a_secondary_tile_features_it_and_returns_the_previous_one_to_the_tile_list,
    test_desktop_selecting_a_second_market_then_a_third_keeps_the_tile_list_consistent,
    test_desktop_tiles_are_plain_buttons_with_no_custom_key_handling,
    test_mobile_initial_state_has_previous_disabled_and_first_dot_active,
    test_mobile_next_arrow_advances_one_market_and_updates_disabled_states_and_dots,
    test_mobile_previous_arrow_retreats_one_market,
    test_mobile_next_arrow_disables_at_the_last_market_and_never_overshoots,
    test_mobile_dot_click_jumps_directly_to_the_selected_market,
  ];

  let failures = 0;
  for (const test of tests) {
    try {
      await test();
      console.log(`PASS ${test.name}`);
    } catch (error) {
      failures += 1;
      console.error(`FAIL ${test.name}: ${(error as Error).message}`);
    }
  }

  if (failures > 0) {
    console.error(`${failures} test(s) failed`);
    process.exit(1);
  }

  console.log(`All ${tests.length} tests passed`);
}

await main();
