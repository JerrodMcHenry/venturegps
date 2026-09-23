"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";

import PageHeader from "@/components/layout/PageHeader";
import BaseCard from "@/components/ui/BaseCard";
import Button from "@/components/ui/Button";

import {
  classifyCompany,
  decideCompanyCandidate,
  decideFinancingCandidate,
  getCompanyCandidateDetail,
  getFinancingCandidateDetail,
  listPendingCompanyCandidates,
  listPendingFinancingCandidates,
  listReviewMarkets,
  listReviewTaxonomyVersions,
  type CompanyCandidateDetail,
  type CompanyCandidateSummary,
  type CompanyDecisionAction,
  type EvidenceExcerpt,
  type FinancingCandidateDetail,
  type FinancingCandidateSummary,
  type FinancingDecisionAction,
  type MarketOut,
} from "@/lib/api/v2/review";

// Increment 18.4 -- internal evidence review interface. Deliberately plain: this mirrors
// AdminAnalyticsView's own "operational, not beautiful" internal-tooling standard, not a new
// polished product surface. It implements NO canonical business rule of its own -- every
// create/attach/reject/defer/classify call goes straight to the backend's existing, unmodified
// promotion/classification services (app/v2_review_api.py), and every read is re-verified
// server-side against the live evidence bytes on every load.

type Tab = "company" | "financing";

function isAccessDenied(err: unknown): boolean {
  return err instanceof Error && /\(403\)/.test(err.message);
}

function Evidence({ label, excerpt }: { label: string; excerpt: EvidenceExcerpt | null | undefined }) {
  if (!excerpt) return null;
  return (
    <div className="rounded-lg border border-border bg-surface-subtle p-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-text-muted">
        {label} <span className="font-normal normal-case text-success">-- verified against live evidence</span>
      </div>
      <blockquote className="mt-1 whitespace-pre-wrap font-mono text-sm text-text-primary">
        &ldquo;{excerpt.text}&rdquo;
      </blockquote>
      <div className="mt-1 text-xs text-text-muted">
        bytes {excerpt.byte_start}&ndash;{excerpt.byte_end}
      </div>
    </div>
  );
}

function ConfirmAndSubmit({
  label,
  disabled,
  submitting,
  onSubmit,
}: {
  label: string;
  disabled: boolean;
  submitting: boolean;
  onSubmit: () => void;
}) {
  const [confirmed, setConfirmed] = useState(false);
  useEffect(() => {
    Promise.resolve().then(() => setConfirmed(false));
  }, [label]);
  return (
    <div className="mt-3 flex flex-col gap-2 border-t border-border pt-3">
      <label className="flex items-start gap-2 text-sm text-text-secondary">
        <input
          type="checkbox"
          className="mt-0.5"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        I have reviewed the evidence above and confirm this decision.
      </label>
      <Button
        variant="primary"
        size="sm"
        disabled={disabled || !confirmed || submitting}
        loading={submitting}
        onClick={() => {
          onSubmit();
          setConfirmed(false);
        }}
      >
        {label}
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------- company candidates

function CompanyCandidatePanel({ token }: { token: string }) {
  const [items, setItems] = useState<CompanyCandidateSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<CompanyCandidateDetail | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [accessDenied, setAccessDenied] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const [action, setAction] = useState<CompanyDecisionAction>("create");
  const [attachCompanyId, setAttachCompanyId] = useState("");
  const [reasonCode, setReasonCode] = useState("");

  const [markets, setMarkets] = useState<MarketOut[]>([]);
  const [taxonomyVersions, setTaxonomyVersions] = useState<string[]>([]);
  const [classifyMarketId, setClassifyMarketId] = useState("");
  const [classifyTaxonomyVersion, setClassifyTaxonomyVersion] = useState("");
  const [classifySubmitting, setClassifySubmitting] = useState(false);
  const [classifyMessage, setClassifyMessage] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setListError(null);
    try {
      const data = await listPendingCompanyCandidates(token);
      setItems(data);
    } catch (err) {
      if (isAccessDenied(err)) setAccessDenied(true);
      else setListError("Couldn't load pending company candidates.");
    }
  }, [token]);

  const loadDetail = useCallback(
    async (id: number) => {
      setDetailError(null);
      setDetail(null);
      try {
        const data = await getCompanyCandidateDetail(token, id);
        setDetail(data);
      } catch (err) {
        if (isAccessDenied(err)) setAccessDenied(true);
        else setDetailError("Couldn't load this candidate's evidence (it may have failed re-verification).");
      }
    },
    [token]
  );

  useEffect(() => {
    Promise.resolve().then(() => {
      loadList();
      listReviewMarkets(token).then(setMarkets).catch(() => {});
      listReviewTaxonomyVersions(token).then(setTaxonomyVersions).catch(() => {});
    });
  }, [loadList, token]);

  useEffect(() => {
    Promise.resolve().then(() => {
      if (selectedId !== null) loadDetail(selectedId);
    });
  }, [selectedId, loadDetail]);

  const submit = async () => {
    if (selectedId === null) return;
    setSubmitting(true);
    setActionMessage(null);
    try {
      const result = await decideCompanyCandidate(token, selectedId, {
        action,
        company_id: action === "attach" ? attachCompanyId : undefined,
        reason_code: action === "reject" || action === "defer" ? reasonCode : undefined,
      });
      setActionMessage(`Recorded: ${result.decision_kind}${result.company_id ? ` (company ${result.company_id})` : ""}`);
      await loadList();
      await loadDetail(selectedId);
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : "The decision could not be recorded.");
    } finally {
      setSubmitting(false);
    }
  };

  const latestCompanyId = detail?.decisions.find((d) => d.company_id)?.company_id ?? null;

  const submitClassification = async () => {
    if (!latestCompanyId || !classifyMarketId || !classifyTaxonomyVersion) return;
    setClassifySubmitting(true);
    setClassifyMessage(null);
    try {
      await classifyCompany(token, latestCompanyId, {
        market_id: classifyMarketId,
        taxonomy_version: classifyTaxonomyVersion,
        role: "primary",
      });
      setClassifyMessage("Primary market classification recorded.");
    } catch (err) {
      setClassifyMessage(err instanceof Error ? err.message : "Classification could not be recorded.");
    } finally {
      setClassifySubmitting(false);
    }
  };

  if (accessDenied) return <AccessDenied />;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
      <BaseCard className="p-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          Pending company candidates
        </h2>
        {listError ? <p className="mt-2 text-sm text-danger">{listError}</p> : null}
        <ul className="mt-2 flex flex-col gap-1">
          {items.map((c) => (
            <li key={c.id}>
              <button
                onClick={() => setSelectedId(c.id)}
                className={`w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-surface-muted ${
                  selectedId === c.id ? "bg-surface-muted font-medium" : ""
                }`}
              >
                <div className="text-text-primary">{c.proposed_name}</div>
                <div className="text-xs text-text-muted">
                  #{c.id} &middot; {c.resolution_state} &middot; {new Date(c.created_at).toLocaleString()}
                </div>
              </button>
            </li>
          ))}
          {items.length === 0 && !listError ? (
            <li className="px-3 py-2 text-sm text-text-muted">No pending candidates.</li>
          ) : null}
        </ul>
      </BaseCard>

      <BaseCard className="p-5">
        {selectedId === null ? (
          <p className="text-sm text-text-muted">Select a candidate to review its evidence.</p>
        ) : detailError ? (
          <p className="text-sm text-danger">{detailError}</p>
        ) : !detail ? (
          <p className="text-sm text-text-muted">Loading&hellip;</p>
        ) : (
          <div className="flex flex-col gap-4">
            <div>
              <h2 className="text-lg font-semibold text-text-primary">{detail.proposed_name}</h2>
              <p className="text-xs text-text-muted">
                Candidate #{detail.id} &middot; state: {detail.resolution_state} &middot; source{" "}
                {detail.provenance.source.name} ({detail.provenance.source.source_key})
              </p>
            </div>

            <Evidence label="Proposed name" excerpt={detail.name_evidence} />
            {detail.identifiers.map((id, i) => (
              <Evidence key={i} label={`Identifier: ${id.identifier_type} = ${id.value}`} excerpt={id.evidence} />
            ))}

            {detail.identity_matches.some((m) => m.matching_company_ids.length > 0) ? (
              <div className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm text-text-primary">
                <div className="font-semibold">Possible existing company match</div>
                {detail.identity_matches
                  .filter((m) => m.matching_company_ids.length > 0)
                  .map((m, i) => (
                    <div key={i} className="mt-1 font-mono text-xs">
                      {m.identifier_type}={m.value} &rarr; {m.matching_company_ids.join(", ")}
                    </div>
                  ))}
              </div>
            ) : null}

            {detail.decisions.length > 0 ? (
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted">Decision history</h3>
                <ul className="mt-1 flex flex-col gap-1 text-sm text-text-secondary">
                  {detail.decisions.map((d) => (
                    <li key={d.id} className="font-mono text-xs">
                      {d.created_at} &middot; {d.decision_kind} &middot; by {d.authority_id}
                      {d.reason_code ? ` (${d.reason_code})` : ""}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {detail.resolution_state === "unresolved" || detail.resolution_state === "deferred" ? (
              <div className="rounded-xl border border-border p-4">
                <h3 className="text-sm font-semibold text-text-primary">Record a decision</h3>
                <div className="mt-2 flex flex-col gap-2">
                  <select
                    className="rounded-lg border border-border bg-surface px-3 py-2 text-sm"
                    value={action}
                    onChange={(e) => setAction(e.target.value as CompanyDecisionAction)}
                  >
                    <option value="create">Create new canonical company</option>
                    <option value="attach">Attach to existing company</option>
                    <option value="defer">Defer (need more evidence)</option>
                    <option value="reject">Reject (not a real company)</option>
                  </select>
                  {action === "attach" ? (
                    <input
                      className="rounded-lg border border-border bg-surface px-3 py-2 text-sm font-mono"
                      placeholder="Existing company UUID"
                      value={attachCompanyId}
                      onChange={(e) => setAttachCompanyId(e.target.value)}
                    />
                  ) : null}
                  {action === "reject" || action === "defer" ? (
                    <input
                      className="rounded-lg border border-border bg-surface px-3 py-2 text-sm"
                      placeholder="Reason code (e.g. zztest_not_a_real_company)"
                      value={reasonCode}
                      onChange={(e) => setReasonCode(e.target.value)}
                    />
                  ) : null}
                </div>
                <ConfirmAndSubmit
                  label="Submit decision"
                  submitting={submitting}
                  disabled={action === "attach" ? !attachCompanyId : (action === "reject" || action === "defer") ? !reasonCode : false}
                  onSubmit={submit}
                />
                {actionMessage ? <p className="mt-2 text-sm text-text-secondary">{actionMessage}</p> : null}
              </div>
            ) : null}

            {latestCompanyId ? (
              <div className="rounded-xl border border-border p-4">
                <h3 className="text-sm font-semibold text-text-primary">
                  Classify company ({latestCompanyId}) into a primary market
                </h3>
                <div className="mt-2 flex flex-col gap-2">
                  <select
                    className="rounded-lg border border-border bg-surface px-3 py-2 text-sm"
                    value={classifyMarketId}
                    onChange={(e) => setClassifyMarketId(e.target.value)}
                  >
                    <option value="">Select a market&hellip;</option>
                    {markets.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.display_name}
                      </option>
                    ))}
                  </select>
                  <select
                    className="rounded-lg border border-border bg-surface px-3 py-2 text-sm"
                    value={classifyTaxonomyVersion}
                    onChange={(e) => setClassifyTaxonomyVersion(e.target.value)}
                  >
                    <option value="">Select a taxonomy version&hellip;</option>
                    {taxonomyVersions.map((v) => (
                      <option key={v} value={v}>
                        {v}
                      </option>
                    ))}
                  </select>
                </div>
                <ConfirmAndSubmit
                  label="Classify as primary"
                  submitting={classifySubmitting}
                  disabled={!classifyMarketId || !classifyTaxonomyVersion}
                  onSubmit={submitClassification}
                />
                {classifyMessage ? <p className="mt-2 text-sm text-text-secondary">{classifyMessage}</p> : null}
              </div>
            ) : null}
          </div>
        )}
      </BaseCard>
    </div>
  );
}

// ---------------------------------------------------------------- financing candidates

function FinancingCandidatePanel({ token }: { token: string }) {
  const [items, setItems] = useState<FinancingCandidateSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<FinancingCandidateDetail | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [accessDenied, setAccessDenied] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const [action, setAction] = useState<FinancingDecisionAction>("create_event");
  const [eventId, setEventId] = useState("");
  const [reasonCode, setReasonCode] = useState("");
  const [acceptStage, setAcceptStage] = useState(true);
  const [acceptType, setAcceptType] = useState(true);
  const [acceptAmount, setAcceptAmount] = useState(true);

  const loadList = useCallback(async () => {
    setListError(null);
    try {
      setItems(await listPendingFinancingCandidates(token));
    } catch (err) {
      if (isAccessDenied(err)) setAccessDenied(true);
      else setListError("Couldn't load pending financing candidates.");
    }
  }, [token]);

  const loadDetail = useCallback(
    async (id: number) => {
      setDetailError(null);
      setDetail(null);
      try {
        setDetail(await getFinancingCandidateDetail(token, id));
      } catch (err) {
        if (isAccessDenied(err)) setAccessDenied(true);
        else setDetailError("Couldn't load this candidate's evidence (it may have failed re-verification).");
      }
    },
    [token]
  );

  useEffect(() => {
    Promise.resolve().then(() => {
      loadList();
    });
  }, [loadList]);

  useEffect(() => {
    Promise.resolve().then(() => {
      if (selectedId !== null) loadDetail(selectedId);
    });
  }, [selectedId, loadDetail]);

  const submit = async () => {
    if (selectedId === null) return;
    setSubmitting(true);
    setActionMessage(null);
    try {
      const result = await decideFinancingCandidate(token, selectedId, {
        action,
        event_id: action === "attach_to_event" ? eventId : undefined,
        reason_code: action === "reject" || action === "defer" ? reasonCode : undefined,
        facts:
          action === "create_event" || action === "attach_to_event"
            ? {
                stage: acceptStage,
                financing_type: acceptType,
                verified_round_amount: acceptAmount,
                dates: detail?.dates.map((d) => d.kind as "first_sale_date" | "filing_date" | "announcement_date"),
              }
            : undefined,
      });
      setActionMessage(`Recorded: ${result.decision_kind}${result.financing_event_id ? ` (event ${result.financing_event_id})` : ""}`);
      await loadList();
      await loadDetail(selectedId);
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : "The decision could not be recorded.");
    } finally {
      setSubmitting(false);
    }
  };

  if (accessDenied) return <AccessDenied />;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
      <BaseCard className="p-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          Pending financing candidates
        </h2>
        {listError ? <p className="mt-2 text-sm text-danger">{listError}</p> : null}
        <ul className="mt-2 flex flex-col gap-1">
          {items.map((c) => (
            <li key={c.id}>
              <button
                onClick={() => setSelectedId(c.id)}
                className={`w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-surface-muted ${
                  selectedId === c.id ? "bg-surface-muted font-medium" : ""
                }`}
              >
                <div className="font-mono text-xs text-text-primary">company {c.company_id}</div>
                <div className="text-xs text-text-muted">
                  #{c.id} &middot; {c.resolution_state} &middot; {new Date(c.created_at).toLocaleString()}
                </div>
              </button>
            </li>
          ))}
          {items.length === 0 && !listError ? (
            <li className="px-3 py-2 text-sm text-text-muted">No pending candidates.</li>
          ) : null}
        </ul>
      </BaseCard>

      <BaseCard className="p-5">
        {selectedId === null ? (
          <p className="text-sm text-text-muted">Select a candidate to review its evidence.</p>
        ) : detailError ? (
          <p className="text-sm text-danger">{detailError}</p>
        ) : !detail ? (
          <p className="text-sm text-text-muted">Loading&hellip;</p>
        ) : (
          <div className="flex flex-col gap-4">
            <div>
              <h2 className="text-lg font-semibold text-text-primary">Financing candidate #{detail.id}</h2>
              <p className="text-xs text-text-muted">
                Company {detail.company_id} &middot;{" "}
                {detail.company_is_canonical ? (
                  <span className="text-success">canonical -- eligible for review</span>
                ) : (
                  <span className="text-danger">not canonical -- decisions blocked server-side</span>
                )}
                {" "}&middot; state: {detail.resolution_state}
              </p>
            </div>

            <Evidence label="Financing occurrence" excerpt={detail.event_evidence} />
            {detail.stage ? <Evidence label={`Stage: ${detail.stage}`} excerpt={detail.stage_evidence} /> : null}
            {detail.financing_type ? (
              <Evidence label={`Financing type: ${detail.financing_type}`} excerpt={detail.financing_type_evidence} />
            ) : null}
            {detail.amounts.map((a, i) => (
              <Evidence
                key={i}
                label={`${a.semantics}: ${a.currency_code} ${(a.minor_units / 100).toLocaleString()}`}
                excerpt={a.evidence}
              />
            ))}
            {detail.dates.map((d, i) => (
              <Evidence key={i} label={`${d.kind} (${d.precision})`} excerpt={d.evidence} />
            ))}

            {detail.decisions.length > 0 ? (
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted">Decision history</h3>
                <ul className="mt-1 flex flex-col gap-1 text-sm text-text-secondary">
                  {detail.decisions.map((d) => (
                    <li key={d.id} className="font-mono text-xs">
                      {d.created_at} &middot; {d.decision_kind} &middot; by {d.authority_id}
                      {d.reason_code ? ` (${d.reason_code})` : ""}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {(detail.resolution_state === "unresolved" || detail.resolution_state === "deferred") &&
            detail.company_is_canonical ? (
              <div className="rounded-xl border border-border p-4">
                <h3 className="text-sm font-semibold text-text-primary">Record a decision</h3>
                <div className="mt-2 flex flex-col gap-2">
                  <select
                    className="rounded-lg border border-border bg-surface px-3 py-2 text-sm"
                    value={action}
                    onChange={(e) => setAction(e.target.value as FinancingDecisionAction)}
                  >
                    <option value="create_event">Create new financing event</option>
                    <option value="attach_to_event">Attach to existing event of this company</option>
                    <option value="defer">Defer (need more evidence)</option>
                    <option value="reject">Reject (not a real financing)</option>
                  </select>
                  {action === "attach_to_event" ? (
                    <select
                      className="rounded-lg border border-border bg-surface px-3 py-2 text-sm font-mono"
                      value={eventId}
                      onChange={(e) => setEventId(e.target.value)}
                    >
                      <option value="">Select existing event&hellip;</option>
                      {detail.existing_events.map((id) => (
                        <option key={id} value={id}>
                          {id}
                        </option>
                      ))}
                    </select>
                  ) : null}
                  {action === "reject" || action === "defer" ? (
                    <input
                      className="rounded-lg border border-border bg-surface px-3 py-2 text-sm"
                      placeholder="Reason code"
                      value={reasonCode}
                      onChange={(e) => setReasonCode(e.target.value)}
                    />
                  ) : null}
                  {action === "create_event" || action === "attach_to_event" ? (
                    <div className="flex flex-col gap-1 text-sm text-text-secondary">
                      <span className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                        Accept these proposed facts as canonical
                      </span>
                      {detail.stage ? (
                        <label className="flex items-center gap-2">
                          <input type="checkbox" checked={acceptStage} onChange={(e) => setAcceptStage(e.target.checked)} />
                          Stage: {detail.stage}
                        </label>
                      ) : null}
                      {detail.financing_type ? (
                        <label className="flex items-center gap-2">
                          <input type="checkbox" checked={acceptType} onChange={(e) => setAcceptType(e.target.checked)} />
                          Financing type: {detail.financing_type}
                        </label>
                      ) : null}
                      {detail.amounts.some((a) => a.semantics === "announced_round_amount") ? (
                        <label className="flex items-center gap-2">
                          <input type="checkbox" checked={acceptAmount} onChange={(e) => setAcceptAmount(e.target.checked)} />
                          Accept announced amount as the verified round amount
                        </label>
                      ) : null}
                    </div>
                  ) : null}
                </div>
                <ConfirmAndSubmit
                  label="Submit decision"
                  submitting={submitting}
                  disabled={action === "attach_to_event" ? !eventId : (action === "reject" || action === "defer") ? !reasonCode : false}
                  onSubmit={submit}
                />
                {actionMessage ? <p className="mt-2 text-sm text-text-secondary">{actionMessage}</p> : null}
              </div>
            ) : null}
          </div>
        )}
      </BaseCard>
    </div>
  );
}

function AccessDenied() {
  return (
    <BaseCard className="p-6">
      <p className="text-sm text-text-secondary">
        Access denied. This internal review interface is restricted to VentureGPS administrators.
      </p>
    </BaseCard>
  );
}

export default function V2ReviewView() {
  const { getToken } = useAuth();
  const [tab, setTab] = useState<Tab>("company");
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.resolve().then(async () => {
      try {
        const t = await getToken();
        if (!t) {
          setError("Your session expired. Sign in again.");
          return;
        }
        setToken(t);
      } catch {
        setError("Couldn't establish a session.");
      }
    });
  }, [getToken]);

  return (
    <div>
      <PageHeader
        title="V2 evidence review"
        subtitle="Internal-only. Review source evidence and decide candidate companies, financing events and market classifications. Every decision is recorded under your own admin identity and cannot be undone by re-submitting."
      />
      {error ? (
        <p className="text-sm text-danger">{error}</p>
      ) : !token ? (
        <p className="text-sm text-text-muted">Loading&hellip;</p>
      ) : (
        <>
          <div className="mb-4 flex gap-2">
            <Button variant={tab === "company" ? "primary" : "secondary"} size="sm" onClick={() => setTab("company")}>
              Company candidates
            </Button>
            <Button variant={tab === "financing" ? "primary" : "secondary"} size="sm" onClick={() => setTab("financing")}>
              Financing candidates
            </Button>
          </div>
          {tab === "company" ? <CompanyCandidatePanel token={token} /> : <FinancingCandidatePanel token={token} />}
        </>
      )}
    </div>
  );
}
