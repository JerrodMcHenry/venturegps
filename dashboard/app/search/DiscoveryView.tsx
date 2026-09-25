"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@clerk/nextjs";

import BaseCard from "@/components/ui/BaseCard";
import DiscoveryResultCard from "@/components/discovery/DiscoveryResultCard";
import CompareSelectionBar from "@/components/discovery/CompareSelectionBar";
import { PILLARS } from "@/components/startup/pillarMeta";
import { useComparisonSelection } from "@/lib/hooks/useComparisonSelection";

import {
  discoverStartups,
  getDiscoveryFilterOptions,
} from "@/lib/api";

import type {
  DiscoveryFilterOptions,
  DiscoveryFilters,
  DiscoveryResult,
  DiscoverySort,
} from "@/types";

const DEFAULT_SORT: DiscoverySort = "sps_desc";
const DEFAULT_LIMIT = 24;
const LOAD_MORE_STEP = 24;
const MAX_LIMIT = 100;

const SORT_OPTIONS: { value: DiscoverySort; label: string }[] = [
  { value: "sps_desc", label: "SPS: high to low" },
  { value: "sps_asc", label: "SPS: low to high" },
  { value: "newest", label: "Newest analysis" },
  { value: "name_asc", label: "Company: A–Z" },
];

// Pillar-minimum filters, in the same order/labels as
// components/startup/pillarMeta.ts's PILLARS -- one source of truth for
// pillar naming across the app, just remapped onto discover_startups()'s
// existing min_<pillar> query-parameter names.
const PILLAR_FILTER_FIELDS: { key: keyof DiscoveryFilters; label: string }[] =
  PILLARS.map((pillar) => ({
    key: (pillar.key === "financial_health"
      ? "min_financial_health"
      : `min_${pillar.key}`) as keyof DiscoveryFilters,
    label: pillar.label,
  }));

// --- URL <-> filters -------------------------------------------------------

const NUMERIC_FILTER_KEYS: (keyof DiscoveryFilters)[] = [
  "min_sps",
  "max_sps",
  "min_market",
  "min_team",
  "min_product",
  "min_execution",
  "min_traction",
  "min_financial_health",
];

const VALID_SORTS: DiscoverySort[] = ["sps_desc", "sps_asc", "newest", "name_asc"];

function parseFiltersFromSearchParams(
  searchParams: URLSearchParams
): DiscoveryFilters {
  const filters: DiscoveryFilters = {};

  const query = searchParams.get("query");
  if (query) {
    filters.query = query;
  }

  const industry = searchParams.get("industry");
  if (industry) {
    filters.industry = industry;
  }

  const stage = searchParams.get("stage");
  if (stage) {
    filters.stage = stage;
  }

  const businessModel = searchParams.get("business_model");
  if (businessModel) {
    filters.business_model = businessModel;
  }

  for (const key of NUMERIC_FILTER_KEYS) {
    const raw = searchParams.get(key);

    if (raw === null || raw === "") {
      continue;
    }

    const value = Number(raw);

    if (!Number.isNaN(value)) {
      // Every key in NUMERIC_FILTER_KEYS maps to a `number | undefined`
      // field on DiscoveryFilters -- TS can't verify that across a keyof
      // union from a runtime loop variable, so this narrows explicitly
      // rather than widening the whole `filters` object's type.
      (filters as Record<string, unknown>)[key] = value;
    }
  }

  const sort = searchParams.get("sort");
  if (sort && (VALID_SORTS as string[]).includes(sort)) {
    filters.sort = sort as DiscoverySort;
  }

  return filters;
}

function filtersToSearchParams(filters: DiscoveryFilters): URLSearchParams {
  const params = new URLSearchParams();

  if (filters.query) {
    params.set("query", filters.query);
  }

  if (filters.industry) {
    params.set("industry", filters.industry);
  }

  if (filters.stage) {
    params.set("stage", filters.stage);
  }

  if (filters.business_model) {
    params.set("business_model", filters.business_model);
  }

  for (const key of NUMERIC_FILTER_KEYS) {
    const value = filters[key];

    if (typeof value === "number" && !Number.isNaN(value)) {
      params.set(key, String(value));
    }
  }

  // Default sort is left out of the URL -- keeps a filters-only URL clean
  // (e.g. /search?industry=Fintech, not
  // /search?industry=Fintech&sort=sps_desc).
  if (filters.sort && filters.sort !== DEFAULT_SORT) {
    params.set("sort", filters.sort);
  }

  return params;
}

function hasAnyFilter(filters: DiscoveryFilters): boolean {
  return Boolean(
    filters.query ||
      filters.industry ||
      filters.stage ||
      filters.business_model ||
      typeof filters.min_sps === "number" ||
      typeof filters.max_sps === "number" ||
      typeof filters.min_market === "number" ||
      typeof filters.min_team === "number" ||
      typeof filters.min_product === "number" ||
      typeof filters.min_execution === "number" ||
      typeof filters.min_traction === "number" ||
      typeof filters.min_financial_health === "number"
  );
}

function hasAnyPillarFilter(filters: DiscoveryFilters): boolean {
  return PILLAR_FILTER_FIELDS.some(
    (field) => typeof filters[field.key] === "number"
  );
}

// Human-readable label for one active-filter pill.
function describeFilter(key: keyof DiscoveryFilters, value: unknown): string {
  const pillarField = PILLAR_FILTER_FIELDS.find((field) => field.key === key);

  if (pillarField) {
    return `${pillarField.label} ≥ ${value}`;
  }

  switch (key) {
    case "query":
      return `"${value}"`;
    case "industry":
      return `Industry: ${value}`;
    case "stage":
      return `Stage: ${value}`;
    case "business_model":
      return `Business model: ${value}`;
    case "min_sps":
      return `SPS ≥ ${value}`;
    case "max_sps":
      return `SPS ≤ ${value}`;
    default:
      return String(value);
  }
}

const ACTIVE_FILTER_KEYS: (keyof DiscoveryFilters)[] = [
  "query",
  "industry",
  "stage",
  "business_model",
  "min_sps",
  "max_sps",
  ...PILLAR_FILTER_FIELDS.map((field) => field.key),
];

type LoadState = "loading" | "ready" | "error";

export default function DiscoveryView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const searchParamsKey = searchParams.toString();

  const filters = parseFiltersFromSearchParams(searchParams);
  const activeSort = filters.sort ?? DEFAULT_SORT;

  const [filterOptions, setFilterOptions] =
    useState<DiscoveryFilterOptions | null>(null);
  const [results, setResults] = useState<DiscoveryResult[]>([]);
  const [total, setTotal] = useState(0);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [limit, setLimit] = useState(DEFAULT_LIMIT);
  const [moreFiltersOpen, setMoreFiltersOpen] = useState(false);
  const compareSelection = useComparisonSelection();
  // Portfolio Release Task 3B -- Secure Analysis Visibility: both
  // endpoints below now require auth and return only this caller's own
  // authorized analyses (approved decision -- no public scores-only
  // exception).
  const { getToken } = useAuth();

  // Filter option lists load once -- they're derived from the whole
  // canonical population, not from the current filter selection, so they
  // never need to be refetched when filters change.
  useEffect(() => {
    let isMounted = true;

    async function loadFilterOptions() {
      try {
        const token = await getToken();
        const options = await getDiscoveryFilterOptions(token);

        if (isMounted) {
          setFilterOptions(options);
        }
      } catch (error) {
        console.error("Failed to load discovery filter options:", error);
        // Non-fatal: the filter selects just render with no options.
      }
    }

    loadFilterOptions();

    return () => {
      isMounted = false;
    };
  }, [getToken]);

  // Refetches whenever the URL (the single source of truth for committed
  // filters) or the local "how many results to show" limit changes.
  useEffect(() => {
    let isMounted = true;

    async function loadResults() {
      if (isMounted) {
        setLoadState("loading");
      }

      try {
        const committedFilters = parseFiltersFromSearchParams(
          new URLSearchParams(searchParamsKey)
        );

        const token = await getToken();
        const response = await discoverStartups(
          {
            ...committedFilters,
            limit,
          },
          token
        );

        if (isMounted) {
          setResults(response.results);
          setTotal(response.total);
          setLoadState("ready");
        }
      } catch (error) {
        console.error("Failed to load discovery results:", error);

        if (isMounted) {
          setResults([]);
          setLoadState("error");
        }
      }
    }

    loadResults();

    return () => {
      isMounted = false;
    };
  }, [searchParamsKey, limit, getToken]);

  function updateFilters(next: DiscoveryFilters) {
    const params = filtersToSearchParams(next);
    const queryString = params.toString();
    router.replace(queryString ? `${pathname}?${queryString}` : pathname, {
      scroll: false,
    });
  }

  function commitFilter(key: keyof DiscoveryFilters, value: string | number | undefined) {
    const next: DiscoveryFilters = { ...filters };

    if (value === undefined || value === "") {
      delete next[key];
    } else {
      // TS can't narrow `next[key] = value` across a union of differently
      // -typed optional fields from a single call site -- every field this
      // function is ever called with is either string|undefined or
      // number|undefined, so the cast here is safe, not a real `any` escape.
      (next as Record<string, unknown>)[key] = value;
    }

    updateFilters(next);
  }

  function commitNumberFilter(key: keyof DiscoveryFilters, rawValue: string) {
    if (rawValue.trim() === "") {
      commitFilter(key, undefined);
      return;
    }

    const parsed = Number(rawValue);

    if (Number.isNaN(parsed)) {
      return;
    }

    commitFilter(key, parsed);
  }

  function handleClearAll() {
    router.replace(pathname, { scroll: false });
  }

  function handleRemoveFilter(key: keyof DiscoveryFilters) {
    commitFilter(key, undefined);
  }

  const isFilterActive = hasAnyFilter(filters);
  const showMoreFilters = moreFiltersOpen || hasAnyPillarFilter(filters);
  const canLoadMore = results.length < total && limit < MAX_LIMIT;

  return (
    <div className="space-y-6">
      <BaseCard className="space-y-5 p-5 sm:p-6">
        {/* Primary filters -- always visible, per Part 8's progressive
            disclosure requirement: the most important controls first, the
            six pillar-minimum filters behind "More Filters" below. */}
        <div>
          <label htmlFor="discovery-query" className="sr-only">
            Search startups
          </label>

          <input
            key={`query-${searchParamsKey}`}
            id="discovery-query"
            type="search"
            defaultValue={filters.query ?? ""}
            placeholder="Search startups by name..."
            onBlur={(event) => commitFilter("query", event.target.value.trim())}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                commitFilter("query", event.currentTarget.value.trim());
              }
            }}
            className="min-h-11 w-full rounded-lg border border-border bg-surface px-4 text-text-primary outline-none transition-colors placeholder:text-text-muted focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/20"
          />
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <FilterSelect
            label="Industry"
            value={filters.industry ?? ""}
            options={filterOptions?.industries ?? []}
            onChange={(value) => commitFilter("industry", value || undefined)}
          />

          <FilterSelect
            label="Stage"
            value={filters.stage ?? ""}
            options={filterOptions?.stages ?? []}
            onChange={(value) => commitFilter("stage", value || undefined)}
          />

          <FilterSelect
            label="Business Model"
            value={filters.business_model ?? ""}
            options={filterOptions?.business_models ?? []}
            onChange={(value) => commitFilter("business_model", value || undefined)}
          />
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <NumberField
            id="discovery-min-sps"
            label="SPS minimum"
            resetKey={searchParamsKey}
            defaultValue={filters.min_sps}
            min={0}
            max={100}
            step={1}
            onCommit={(value) => commitNumberFilter("min_sps", value)}
          />

          <NumberField
            id="discovery-max-sps"
            label="SPS maximum"
            resetKey={searchParamsKey}
            defaultValue={filters.max_sps}
            min={0}
            max={100}
            step={1}
            onCommit={(value) => commitNumberFilter("max_sps", value)}
          />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
          <button
            type="button"
            onClick={() => setMoreFiltersOpen((open) => !open)}
            aria-expanded={showMoreFilters}
            aria-controls="discovery-more-filters"
            className="text-sm font-semibold text-primary hover:text-primary-hover"
          >
            {showMoreFilters ? "− Fewer filters" : "+ More filters"}
          </button>

          <div className="flex items-center gap-2">
            <label htmlFor="discovery-sort" className="text-sm text-text-secondary">
              Sort
            </label>

            <select
              id="discovery-sort"
              value={activeSort}
              onChange={(event) =>
                commitFilter("sort", event.target.value as DiscoverySort)
              }
              className="h-10 rounded-lg border border-border bg-surface px-3 text-sm text-text-primary outline-none transition-colors focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/20"
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {showMoreFilters ? (
          <div
            id="discovery-more-filters"
            className="grid gap-3 border-t border-border pt-4 sm:grid-cols-3"
          >
            {PILLAR_FILTER_FIELDS.map((field) => (
              <NumberField
                key={field.key}
                id={`discovery-${field.key}`}
                label={`${field.label} minimum`}
                resetKey={searchParamsKey}
                defaultValue={filters[field.key] as number | undefined}
                min={0}
                max={10}
                step={0.1}
                onCommit={(value) => commitNumberFilter(field.key, value)}
              />
            ))}
          </div>
        ) : null}

        {/* Active-filter pills: shows current state explicitly (not just
            via control values) and lets each filter be removed
            individually, plus a single Clear All -- Part 8's UX
            requirements. */}
        {isFilterActive ? (
          <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
            {ACTIVE_FILTER_KEYS.filter(
              (key) => filters[key] !== undefined
            ).map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => handleRemoveFilter(key)}
                className="inline-flex items-center gap-1.5 rounded-full bg-primary-soft px-3 py-1.5 text-xs font-semibold text-primary transition-colors hover:bg-primary/20"
                aria-label={`Remove filter: ${describeFilter(key, filters[key])}`}
              >
                {describeFilter(key, filters[key])}
                <span aria-hidden="true">×</span>
              </button>
            ))}

            <button
              type="button"
              onClick={handleClearAll}
              className="text-xs font-semibold text-text-muted underline-offset-2 hover:text-danger hover:underline"
            >
              Clear all
            </button>
          </div>
        ) : null}
      </BaseCard>

      <ResultsSection
        loadState={loadState}
        results={results}
        total={total}
        isFilterActive={isFilterActive}
        canLoadMore={canLoadMore}
        onLoadMore={() => setLimit((current) => Math.min(current + LOAD_MORE_STEP, MAX_LIMIT))}
        onClearAll={handleClearAll}
        compareSelection={compareSelection}
      />

      <CompareSelectionBar
        selectedIds={compareSelection.selectedIds}
        onClear={compareSelection.clear}
      />
    </div>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  const id = `discovery-filter-${label.toLowerCase().replace(/\s+/g, "-")}`;

  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-text-secondary">
        {label}
      </label>

      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-11 w-full rounded-lg border border-border bg-surface px-3 text-sm text-text-primary outline-none transition-colors focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/20"
      >
        <option value="">All {label.toLowerCase()}</option>

        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  );
}

function NumberField({
  id,
  label,
  resetKey,
  defaultValue,
  min,
  max,
  step,
  onCommit,
}: {
  id: string;
  label: string;
  resetKey: string;
  defaultValue: number | undefined;
  min: number;
  max: number;
  step: number;
  onCommit: (rawValue: string) => void;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-text-secondary">
        {label}
      </label>

      {/* Uncontrolled by design: key={resetKey} (the committed URL's own
          query string) forces React to remount this input -- resetting it
          to defaultValue -- whenever the URL changes for ANY reason
          (another filter committed, Clear All, browser back/forward).
          Typed-but-not-yet-committed digits are never lost to a
          re-render, and no extra state/effect is needed to keep this in
          sync with the URL. */}
      <input
        key={resetKey}
        id={id}
        type="number"
        inputMode="decimal"
        min={min}
        max={max}
        step={step}
        // Product-quality review: a blank number box gives no hint that
        // SPS is 0-100 and pillar scores are 0-10 -- this range is
        // otherwise only documented on the Startup Profile page itself,
        // not here.
        placeholder={`${min}–${max}`}
        defaultValue={defaultValue ?? ""}
        onBlur={(event) => onCommit(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            onCommit(event.currentTarget.value);
          }
        }}
        className="h-11 w-full rounded-lg border border-border bg-surface px-3 text-sm text-text-primary outline-none transition-colors placeholder:text-text-muted focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/20"
      />
    </div>
  );
}

function ResultsSection({
  loadState,
  results,
  total,
  isFilterActive,
  canLoadMore,
  onLoadMore,
  onClearAll,
  compareSelection,
}: {
  loadState: LoadState;
  results: DiscoveryResult[];
  total: number;
  isFilterActive: boolean;
  canLoadMore: boolean;
  onLoadMore: () => void;
  onClearAll: () => void;
  compareSelection: ReturnType<typeof useComparisonSelection>;
}) {
  if (loadState === "loading") {
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, index) => (
          <div
            key={index}
            className="h-48 animate-pulse rounded-2xl border border-border bg-surface"
          />
        ))}
      </div>
    );
  }

  if (loadState === "error") {
    return (
      <div className="rounded-xl border border-danger/20 bg-danger-soft p-6">
        <h2 className="font-semibold text-danger">
          Unable to load discovery results
        </h2>

        <p className="mt-2 text-sm text-danger/80">
          Something went wrong loading startups. Try refreshing the page.
        </p>
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <BaseCard className="p-10 text-center">
        <p className="text-lg font-semibold text-text-primary">
          No startups match these filters
        </p>

        <p className="mx-auto mt-2 max-w-md text-base leading-7 text-text-secondary">
          {isFilterActive
            ? "Try widening your filters -- a lower SPS minimum, a different industry, or clearing a filter entirely."
            : "There are no canonical startup analyses yet."}
        </p>

        {isFilterActive ? (
          <button
            type="button"
            onClick={onClearAll}
            className="mt-5 rounded-xl border border-primary/30 px-4 py-2.5 text-sm font-semibold text-primary transition-colors hover:bg-primary-soft"
          >
            Clear all filters
          </button>
        ) : null}
      </BaseCard>
    );
  }

  return (
    <div className="space-y-5">
      <p className="text-sm text-text-secondary">
        <span className="font-semibold text-text-primary">{total}</span>{" "}
        {total === 1 ? "startup" : "startups"}
      </p>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {results.map((result) => (
          <DiscoveryResultCard
            key={result.startup_id}
            result={result}
            compareSelected={compareSelection.isSelected(result.startup_id)}
            compareDisabled={compareSelection.atMax}
            onToggleCompare={() => compareSelection.toggle(result.startup_id)}
          />
        ))}
      </div>

      {canLoadMore ? (
        <div className="flex justify-center pt-2">
          <button
            type="button"
            onClick={onLoadMore}
            className="rounded-xl border border-border px-5 py-2.5 text-sm font-semibold text-text-secondary transition-colors hover:border-primary hover:text-primary"
          >
            Load more
          </button>
        </div>
      ) : null}
    </div>
  );
}
