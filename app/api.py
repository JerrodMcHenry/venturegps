from datetime import date
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError as PydanticValidationError
from app.database.db import (create_tables,
                         create_score_history_table, 
                         save_analysis, 
                         get_analyses, 
                         get_analysis_by_id, 
                         delete_analysis,
                         update_analysis,
                         search_analyses,
                         add_scoring_columns,
                         add_analysis_columns,
                         get_analytics,
                         get_sps_v3_analytics,
                         add_benchmarking_columns,
                         get_industry_analytics,
                         get_rankings,
                         add_company_name_column,
                         add_readiness_columns,
                         save_score_history,
                         get_score_history,
                         get_startup_trends,
                         get_top_startups,
                         get_top_improving_startups,
                         get_startup_by_name,
                         add_methodology_column,
                         get_sps_history,
                         create_startups_table,
                         add_startup_id_column,
                         add_analysis_submitted_by_column,
                         create_users_table,
                         create_startup_memberships_table,
                         create_saved_startups_table,
                         backfill_startup_ids,
                         save_startup_for_user,
                         unsave_startup_for_user,
                         is_startup_saved_by_user,
                         get_saved_startups_for_user,
                         discover_startups,
                         count_discover_startups,
                         get_discovery_filter_options,
                         DEFAULT_DISCOVERY_LIMIT,
                         MAX_DISCOVERY_LIMIT,
                         get_startups_for_comparison,
                         MIN_COMPARISON_STARTUPS,
                         MAX_COMPARISON_STARTUPS,
                         create_modeled_ventures_table,
                         create_modeled_venture,
                         list_modeled_ventures_for_user,
                         list_active_questions_for_user,
                         get_modeled_venture_for_user,
                         update_modeled_venture_for_user,
                         delete_modeled_venture_for_user,
                         add_venture_share_columns,
                         get_venture_share_settings_for_owner,
                         update_venture_share_settings_for_owner,
                         get_venture_by_share_public_id,
                         create_product_events_table,
                         log_product_event,
                         get_full_analytics_report,
                         create_venture_missions_table,
                         add_mission_idempotency_column,
                         add_pitch_deck_coach_mission_source,
                         list_venture_missions_for_owner,
                         create_venture_mission,
                         update_venture_mission_status_for_owner,
                         record_venture_mission_learning_for_owner,
                         capture_venture_observation,
                         create_venture_model_updates_table,
                         create_venture_model_update,
                         list_venture_model_updates_for_owner,
                         create_startup_claims_table,
                         create_startup_claim,
                         list_startup_claims_for_user,
                         get_startup_claim_status_for_user,
                         list_pending_startup_claims_for_admin,
                         approve_startup_claim,
                         reject_startup_claim,
                         cancel_startup_claim,
                         StartupNotFoundError,
                         DuplicatePendingClaimError,
                         AlreadyMemberError,
                         get_startup_memberships_for_user,
                         user_has_startup_membership,
                         get_founder_startup_workspace,
                         create_founder_actions_table,
                         list_founder_actions_for_startup,
                         create_founder_action,
                         update_founder_action_status,
                         create_founder_updates_table,
                         list_founder_updates_for_startup,
                         create_founder_update,
                         update_founder_update,
                         create_startup_milestones_table,
                         list_startup_milestones_for_startup,
                         create_startup_milestone,
                         update_startup_milestone_status,
                         add_fundraising_gap_source_to_founder_actions,
                         get_watchlist_startups_for_user,
                         create_analysis_runs_table,
                         compute_analysis_fingerprint,
                         count_recent_analysis_runs,
                         has_recent_duplicate_completed_run,
                         begin_analysis_run,
                         finish_analysis_run,
                         DAILY_ANALYSIS_CAP,
                         USAGE_WINDOW_HOURS,
                         create_pitch_deck_reviews_table,
                         create_pitch_deck_review,
                         list_pitch_deck_reviews_for_user,
                         get_pitch_deck_review_for_user,
                         count_recent_pitch_deck_reviews,
                         create_venture_graduations_table,
                         add_venture_graduations_startup_unique_constraint,
                         get_venture_graduation_for_owner,
                         resolve_startup_for_graduation,
                         create_venture_graduation,
                         StartupNameCollisionError,
                         StartupAlreadyGraduatedError,
                         add_venture_intelligence_columns,
                         create_venture_decisions_table,
                         create_venture_evidence_table,
                         create_venture_evidence,
                         list_venture_evidence_for_owner,
                         resolve_venture_evidence_for_owner,
                         create_venture_financial_snapshots_table,
                         add_financial_snapshot_idempotency_column,
                         create_venture_financial_snapshot,
                         get_latest_venture_financial_snapshot_for_owner,
                         list_venture_financial_snapshots_for_owner,
                         create_venture_hire_plans_table,
                         create_venture_hire_plan,
                         list_venture_hire_plans_for_owner,
                         get_venture_hire_plan_for_owner,
                         list_venture_hire_plans_for_owner_by_ids,
                         update_venture_hire_plan_for_owner,
                         add_hire_plan_reconciliation_column,
                         create_venture_financial_plans_table,
                         create_venture_financial_plan,
                         list_venture_financial_plans_for_owner,
                         get_venture_financial_plan_for_owner,
                         list_venture_financial_plans_for_owner_by_ids,
                         update_venture_financial_plan_for_owner,
                         create_venture_financial_scenarios_table,
                         create_venture_financial_scenario,
                         list_venture_financial_scenarios_for_owner,
                         get_venture_financial_scenario_for_owner,
                         update_venture_financial_scenario_for_owner,
                         delete_venture_financial_scenario_for_owner,
                         list_pending_reconciliation_for_owner,
                         create_venture_decision,
                         list_venture_decisions_for_owner,
                         set_venture_mission_interpretation_for_owner,
                         create_venture_financial_commitments_table,
                         create_venture_financial_commitment,
                         list_venture_financial_commitments_for_owner,
                         get_venture_financial_commitment_for_owner,
                         add_financial_commitment_explanation_columns,
                         fix_idempotency_key_scoping_to_prevent_cross_user_replay,
                         update_venture_financial_commitment_explanation_for_owner,
)
from typing import Literal
from fastapi import Query

from app.models.startup import StartupAnalysisRequest, StartupAnalysisResponse, StartupProfileResponse, UpdateAnalysisRequest, WebsiteAnalysisRequest, MAX_COMPANY_TEXT_LENGTH, SavedStartupEntry, SavedStartupStatus, DiscoveryResponse, DiscoveryFilterOptions, ComparisonResponse, ComparisonStartup, ComparisonPillar, ComparisonSubscore
from app.models.sps_v3 import SPSV3Assessment
from app.models.idea_lab import CreateVentureRequest, UpdateVentureRequest, VentureResponse, VentureSummary, VPSResult, ScenarioCompareRequest, ScenarioCompareResponse, StructureIdeaRequest, StructureIdeaResponse, VentureDraft, VentureHistoryResponse, VentureHistoryEvent, VentureHistoryCategoryChange, VentureHistoryAssumptionChange, UpdateVentureShareRequest, VentureShareSettings, VentureSnapshotResponse, VentureSnapshotCategory
from app.models.venture_missions import (
    CreateMissionRequest, UpdateMissionStatusRequest, RecordMissionLearningRequest,
    VentureMissionResponse, CaptureObservationRequest,
    CreateEvidenceRequest, VentureEvidenceResponse, ResolveEvidenceRequest,
    CreateDecisionRequest, VentureDecisionResponse,
    BuildRecommendationResponse, CurrentQuestion, BuildRecommendation,
    CompanyIntelligenceSummary,
)
from app.ai.build_recommendation import build_intelligence_state, generate_interpretation, build_company_intelligence_summary
from app.models.venture_financials import (
    CreateFinancialSnapshotRequest, FinancialSnapshotResponse, DerivedFinancialMetrics,
    ProjectedMonth, VentureFinancialsResponse, FinancialHistoryResponse,
)
from app.models.venture_hire_plans import (
    CreateHirePlanRequest, UpdateHirePlanRequest, HirePlanResponse,
    HireImpactPreview, ProjectedMonthWithPlan,
)
from app.models.venture_financial_plans import (
    CreateFinancialPlanRequest, UpdateFinancialPlanRequest, FinancialPlanResponse,
    CreateScenarioRequest, UpdateScenarioRequest, ScenarioResponse, ScenarioProjectedMonth,
    ReconciliationItem, ReconcilePlanRequest, FinancialPlanImpactPreview,
)
from app.ai.financial_engine import (
    compute_derived_metrics, project_monthly_cash_flow,
    compute_hire_monthly_cost_cents, compute_hire_annual_cost_cents,
    hire_plan_items_for_projection, hire_to_plan_item,
    financial_plan_items_for_projection, expense_plan_to_plan_item, revenue_plan_to_plan_item,
    validate_expense_plan_amount, validate_no_overlapping_revenue_target,
    DEFAULT_PROJECTION_HORIZON_MONTHS, FINANCIAL_PROJECTION_CALCULATION_VERSION,
)
from app.models.venture_financial_commitments import (
    CreateFinancialCommitmentRequest, FinancialCommitmentResponse, PlanSnapshotItem,
    FinancialCommitmentComparisonResponse, UpdateFinancialCommitmentExplanationRequest,
    RelevantHireHistoryResponse,
)
from app.ai.commitment_comparison import build_commitment_comparison
from app.ai.hiring_history import find_relevant_hire_history
from app.models.startup_claim import CreateStartupClaimRequest, StartupClaimSubmissionResponse, MyStartupClaim, StartupClaimStatus, AdminStartupClaim, RejectStartupClaimRequest, StartupClaimActionResponse
from app.models.startup_membership import MyStartupMembership
from app.models.founder import FounderStartupWorkspace
from app.models.venture_graduation import VentureGraduationStatus, GraduateVentureRequest, GraduateVentureResponse
from app.models.founder_action import FounderAction, CreateFounderActionRequest, UpdateFounderActionStatusRequest, FOUNDER_ACTION_PILLARS
from app.models.founder_update import FounderUpdate, CreateFounderUpdateRequest, UpdateFounderUpdateRequest, FOUNDER_UPDATE_PILLARS
from app.models.startup_milestone import StartupMilestone, CreateMilestoneRequest, UpdateMilestoneStatusRequest, MILESTONE_PILLARS
from app.models.fundraising_readiness import FundraisingReadinessResponse, PillarReadinessOut, ReadinessGapOut, ChecklistItemOut
from app.ai.fundraising_readiness import assess_fundraising_readiness
from app.models.investor_workspace import InvestorWorkspaceResponse, InvestorOverviewOut, WatchedStartupOut, PillarChangeOut, RecentChangeOut, AttentionItemOut
from app.ai.investor_workspace import assess_investor_workspace
from app.ai.idea_structuring import structure_idea, IdeaStructuringError
from app.models.pitch_deck_coach import PitchDeckReviewResponse, PitchDeckReviewSummary
from app.ai.pitch_deck_coaching import generate_pitch_deck_review, PitchDeckCoachingError
from app.workflows.due_diligence_workflow import run_due_diligence, assemble_multi_source_text
from app.auth import AuthenticatedUser, RequireAuth, RequireAdmin, RequireStartupMember, require_startup_member, is_admin
from app.ai.sie_v2_methodology import METHODOLOGY_VERSION
from app.ai.vps_scoring import compute_vps
from app.ai.vps_guidance import generate_guidance
import json
import os
import traceback
from app.pdf_extractor import extract_text_from_pdf, extract_pages_from_pdf, MAX_PDF_BYTES, PdfExtractionError
from app.website_scrapper import extract_text_from_website
from app.reporting.pdf_generator import generate_pdf_report
from app.observability import init_observability, capture_exception

# Phase 40C -- Private Beta Deployment + Production Acceptance. Called
# before the app is otherwise configured, matching Sentry's own "as early
# in the process as possible" guidance. No-op when SENTRY_DSN is unset
# (every environment until it's explicitly configured) -- see
# app/observability.py's own docstring.
init_observability()

app = FastAPI()

# Staging Deployment Preparation: local development origins are preserved
# as the default (identical behavior to before, when CORS_ALLOWED_ORIGINS
# is unset), while a deployed backend sets CORS_ALLOWED_ORIGINS to the
# real, deployed frontend origin(s) -- comma-separated, e.g.
# "https://sie-staging.vercel.app,https://app.example.com" -- so the
# origin list never has to be hardcoded or committed here, and never
# widens to a wildcard.
_LOCAL_DEV_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def _resolve_cors_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "")
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or _LOCAL_DEV_CORS_ORIGINS


app.add_middleware(
    CORSMiddleware,
    allow_origins=_resolve_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("RUNNING API.PY MIGRATIONS")

create_tables()
add_analysis_columns()
add_scoring_columns()
add_benchmarking_columns()
add_company_name_column()
add_readiness_columns()
add_methodology_column()
create_score_history_table()

# SIE Accounts & Ownership -- Canonical Startup Entity (first
# implementation slice). Order matters: startups must exist before
# analyses.startup_id can reference it, and users must exist before the
# membership/saved tables that reference it. backfill_startup_ids() runs
# last and is safe to call on every startup (idempotent -- see its own
# docstring in app/database/db.py). No existing canonical read query
# (get_rankings, search_analyses, get_startup_by_name, get_sps_history,
# get_top_improving_startups, get_analytics) is touched by this slice.
create_startups_table()
add_startup_id_column()
create_users_table()
# Portfolio Release Task 3B -- must run after create_users_table() (its FK
# target) and can run any time after that; placed here, immediately after,
# rather than at the end of this migration sequence, so it's obvious the
# dependency is satisfied by construction, not by call-order coincidence.
add_analysis_submitted_by_column()
create_startup_memberships_table()
create_saved_startups_table()
backfill_startup_ids()

# Idea Lab / Venture Simulator V1. modeled_ventures has no FK to
# startups/analyses (see create_modeled_ventures_table()'s own docstring
# in app/database/db.py) -- ordering relative to the migrations above
# only matters because it references users(id), which must already exist.
create_modeled_ventures_table()

# Phase 27 -- Shareable Venture Snapshot V1. Additive columns on the
# table just created above -- must run after it, same reasoning as every
# other add_*_columns() call in this file.
add_venture_share_columns()

# Phase 28 -- Product Analytics & Growth Measurement V1. No FK to
# modeled_ventures/users (see create_product_events_table()'s own
# docstring), so ordering relative to those tables' own migrations
# doesn't strictly matter -- placed here for narrative proximity to the
# venture-track tables whose events it mostly logs.
create_product_events_table()

# Phase 10.7 -- Founder Missions V1. venture_missions FKs to
# modeled_ventures(id), which must already exist by this point (same
# ordering reasoning as modeled_ventures's own migration above).
create_venture_missions_table()

# Phase 40A-FIX -- Private Beta P1 Hardening. Additive column on the
# table just created above.
add_mission_idempotency_column()

# Phase 16 -- Founder Progress / Venture History V1. venture_model_updates
# FKs to both modeled_ventures(id) and venture_missions(id), so it must be
# created after both.
create_venture_model_updates_table()

# Phase 11 -- Pitch Deck Coach V2, Part 13. Widens venture_missions.source
# to allow 'pitch_deck_coach' -- see add_pitch_deck_coach_mission_source()'s
# own docstring in app/database/db.py. Additive only; existing rows and
# every other source value are untouched.
add_pitch_deck_coach_mission_source()

# Phase 34D -- SIE Build Intelligence Loop V1. Additive venture_missions
# columns (question_text, why_it_matters, interpretation_*) + a widened
# mission_type CHECK, then the two new tables the accepted architecture
# (docs/product/SIE_BUILD_INTELLIGENCE_ARCHITECTURE_V1.md §D) calls for.
# venture_decisions must be created before venture_evidence, which
# references it.
add_venture_intelligence_columns()
create_venture_decisions_table()
create_venture_evidence_table()

# Phase 35B -- Financial State Persistence + Runway Engine V1. One new,
# fully independent, append-only table -- no FK to venture_missions/
# venture_evidence/venture_decisions, ordering relative to them doesn't
# matter, only that modeled_ventures already exists.
create_venture_financial_snapshots_table()

# Phase 40A-FIX -- Private Beta P1 Hardening. Additive column on the
# table just created above.
add_financial_snapshot_idempotency_column()

# Phase 35C -- Hiring + Operating Plan Engine V1. A second, independent
# table -- no FK to venture_financial_snapshots (a plan is calculated
# AGAINST actual state, never joined to a specific snapshot row).
create_venture_hire_plans_table()

# Phase 35D -- Operating Scenarios + Financial Plan Reconciliation V1.
# One additive column on the existing (already-populated) hire plans
# table, plus two new, independent tables.
add_hire_plan_reconciliation_column()
create_venture_financial_plans_table()
create_venture_financial_scenarios_table()

# Phase 38D-A -- Financial Commitment Persistence + Frozen Expectation V1.
# Must run AFTER venture_decisions, venture_financial_snapshots,
# venture_financial_scenarios all exist -- this table's own FKs reference
# every one of them.
create_venture_financial_commitments_table()

# Phase 38D-C -- Founder Explanation + Learning Capture V1. Additive
# columns on the table just created above.
add_financial_commitment_explanation_columns()

# Phase 40A-FIX -- Private Beta P1 Hardening / Security Correction. Must
# run after venture_decisions, venture_evidence, and
# venture_financial_commitments all exist (their idempotency_key
# columns/indexes are already present from earlier migrations above --
# this only re-scopes the unique index each already has).
fix_idempotency_key_scoping_to_prevent_cross_user_replay()

# Phase 10.8 -- Pitch Deck Coach V1. pitch_deck_reviews has no FK to
# startups/analyses/modeled_ventures (see create_pitch_deck_reviews_table()'s
# own docstring in app/database/db.py) -- ordering relative to the
# migrations above only matters because it references users(id).
create_pitch_deck_reviews_table()

# Phase 7.1A -- Startup Claim & Membership backend lifecycle. Purely
# additive: references users(id)/startups(id), which already exist by
# this point. Does not alter startup_memberships's existing schema/
# default at all (see create_startup_claims_table()'s own docstring in
# app/database/db.py for why).
create_startup_claims_table()

# Phase 7.3 -- Founder Progress & Improvement V1. Purely additive:
# references startups(id)/users(id), which already exist by this point.
# Never touches startup_memberships or analyses -- see
# create_founder_actions_table()'s own module-level comment in
# app/database/db.py for the full "workflow state, never scoring" boundary.
create_founder_actions_table()

# Phase 7.4 -- Founder Evidence + Milestones V1. Purely additive:
# references startups(id)/users(id), which already exist by this point.
# Never touches startup_memberships or analyses -- see
# create_founder_updates_table()'s/create_startup_milestones_table()'s
# own module-level comment in app/database/db.py for the full
# "founder-reported record, never canonical evidence, never scoring"
# boundary.
create_founder_updates_table()
create_startup_milestones_table()

# Phase 8 -- Fundraising Readiness V1. Widens founder_actions.source to
# allow 'fundraising_gap' (Part 16's Action Plan integration) -- see
# add_fundraising_gap_source_to_founder_actions()'s own docstring in
# app/database/db.py. No new table: readiness itself is computed fresh
# from existing canonical intelligence on every request (see
# app/ai/fundraising_readiness.py's own module docstring for the
# persistence decision), so there is no create_*_table() call for it.
add_fundraising_gap_source_to_founder_actions()

# Phase 10.1B -- AI Cost + Analysis Abuse Protection. Purely additive:
# references users(id)/startups(id), which already exist by this point.
# See create_analysis_runs_table()'s own module-level comment in
# app/database/db.py for the full design record (the partial unique
# index is what makes the concurrency lock durable across processes).
create_analysis_runs_table()

# Phase 31 -- Venture -> Startup Graduation V1. venture_graduations FKs to
# modeled_ventures(id), startups(id), and users(id), all of which already
# exist by this point (modeled_ventures and startups/startup_memberships
# are created above). See create_venture_graduations_table()'s own
# docstring in app/database/db.py for why this is a pure relationship
# record and never a second copy of venture content.
create_venture_graduations_table()

# Phase 31A -- Graduation Integrity Hardening, database invariant #3:
# a startup may be the graduation target of at most one venture. Purely
# additive (see add_venture_graduations_startup_unique_constraint()'s own
# docstring for the try/except-swallow idempotency this shares with every
# other add_*_columns() migration in this file); must run after the
# table above exists.
add_venture_graduations_startup_unique_constraint()

# VentureGPS V2 -- Increment 14: read-only Capital Intelligence API, mounted as its own isolated router
# (app/v2/api.py). No V1 route above or below this line is touched; the V2 router runs no schema migration of
# its own here (V2 schema changes are applied by hand, never at import time, see
# docs/v2/DATABASE_MIGRATIONS.md) and depends only on V2's own read repositories, never on anything above.
from app.v2.api import router as v2_capital_router
app.include_router(v2_capital_router)

# VentureGPS V2 -- Increment 18.4: internal evidence review API (app/v2_review_api.py), mounted the same way.
# Lives on the legacy side (not app/v2/) precisely so it can import app.auth's RequireAdmin -- V2 code itself
# may never import legacy. Every route in it is admin-gated; nothing here is public.
from app.v2_review_api import router as v2_review_router
app.include_router(v2_review_router)

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/version")
def version():
    return {
        "app": "AI Due Diligence Copilot",
        "version": "1.0",
        # P0 Product Trust Cleanup: additive field only -- "version" above
        # is the app version and is left untouched (out of this cleanup's
        # scope). methodology_version reuses the same constant the backend
        # stamps onto every new canonical analysis
        # (app/ai/sie_v2_methodology.py), so the frontend has one safe,
        # already-correct source instead of a second hardcoded string.
        "methodology_version": METHODOLOGY_VERSION,
    }

@app.get("/admin/diagnostics/observability-check")
def observability_check(current_user: AuthenticatedUser = RequireAdmin):
    """
    Phase 40C -- Private Beta Deployment. Admin-only. Deliberately raises,
    so a real server-side exception flows through the exact
    log-and-capture-and-500 path every other endpoint in this file uses
    (traceback.print_exc() + capture_exception() + a generic 500). This
    is the one honest way to confirm production Sentry is actually
    receiving exceptions -- and tagging them with the right environment --
    without waiting for a real founder to hit a bug or spending real
    OpenAI/Tavily budget to force a failure deeper in the stack.

    Takes no body and no query params, and its error reveals nothing
    about the system -- it only proves the exception pipe works. Safe to
    keep permanently: RequireAdmin means only a user_id in ADMIN_USER_IDS
    can reach it, so it is not an abuse or DoS surface.
    """
    try:
        raise RuntimeError(
            "observability-check: intentional test exception (admin-triggered)"
        )
    except Exception as _exc:
        traceback.print_exc()
        capture_exception(_exc)
        raise HTTPException(
            status_code=500,
            detail="Observability check triggered a test error (this is expected).",
        )


@app.get("/")
def health_check():
    return {"status": "API is running"}

# Phase 10.1A -- Critical Security Hardening. These five raw
# analysis-row endpoints predate the canonical Startup/auth architecture
# and are not part of the current product surface -- confirmed by
# repository search that no frontend code calls any of them (the only
# live consumer of the /analyses family is GET /analyses/search, used by
# the public /search page, which is intentionally untouched here: it
# only ever returns company_name/summary/overall_score, the same public
# tier as Rankings/Discovery/Startup Profile).
#
# Analyses belong to canonical startups, not individual users -- there is
# no per-user ownership concept to build here, and inventing one would be
# scope creep this phase explicitly forbids. RequireAdmin is the smallest
# defensible policy: raw row-level read/update/delete of any analysis by
# sequential ID is an administrative/legacy-data-management operation,
# not a signed-in-user workflow, so RequireAuth alone (which only proves
# "this is some authenticated user") would still leave every beta user
# able to read or destroy any other user's/startup's analysis data.
@app.get("/analyses")
def get_saved_analyses(current_user: AuthenticatedUser = RequireAdmin):
    return get_analyses()

# Portfolio Release Task 3B: scoped to the caller's own authorized
# analyses (approved decision) -- previously fully public, and previously
# able to full-text-match against company_text/summary/etc. of every
# analysis on the platform (a narrow existence-probing risk the read-only
# audit flagged). Now RequireAuth; search_analyses() applies the same
# visibility clause as every other scoped read above.
@app.get("/analyses/search")
def search_saved_analyses(query: str, current_user: AuthenticatedUser = RequireAuth):
    return search_analyses(query, current_user.user_id, is_admin(current_user.user_id))

@app.get("/analyses/{analysis_id}")
def get_saved_analysis(analysis_id: int, current_user: AuthenticatedUser = RequireAdmin):
    analysis = get_analysis_by_id(analysis_id)

    if analysis is None:
        return {"error": "Analysis not found"}

    return analysis


@app.get("/analyses/{analysis_id}/pdf")
def download_analysis_pdf(analysis_id: int, current_user: AuthenticatedUser = RequireAdmin):
    analysis = get_analysis_by_id(analysis_id)

    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")

    pdf_path = generate_pdf_report(analysis)

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=pdf_path.split("/")[-1],
    )

# Portfolio Release Task 3B -- Secure Analysis Visibility. get_analytics()
# depends on get_rankings(), which is now viewer-scoped (see that
# function's own comment) -- RequireAuth here is what makes a real
# viewer_user_id/viewer_is_admin available to pass through. Audited but
# deliberately left untouched by this task: /analytics/industries and
# /analytics/sps-v3 (below) return only platform-wide COUNTS with no
# per-company name, score, or narrative text attached -- a materially
# different, lower-risk category than the named-in-scope endpoints
# (rankings/discovery/comparison/search/history all return per-company,
# identifiable results). Revisit separately if that judgment changes.
@app.get("/analytics")
def analytics(current_user: AuthenticatedUser = RequireAuth):
    return get_analytics(current_user.user_id, is_admin(current_user.user_id))

@app.get("/analytics/industries")
def industry_analytics():
    return get_industry_analytics()


# Phase 10.9, Part 23 -- additive, separate from GET /analytics (which
# describes the canonical V2.1 population). See get_sps_v3_analytics()'s
# own docstring in app/database/db.py.
@app.get("/analytics/sps-v3")
def sps_v3_analytics():
    return get_sps_v3_analytics()

# Portfolio Release Task 3B: Rankings is now scoped to the caller's own
# authorized analyses (approved decision -- no public scores-only
# exception), so it requires a verified identity to scope by.
@app.get("/rankings")
def rankings(current_user: AuthenticatedUser = RequireAuth):
    return get_rankings(current_user.user_id, is_admin(current_user.user_id))


# ---------------------------------------------------------------------------
# Startup Discovery V1. Portfolio Release Task 3B: now RequireAuth --
# exploring the canonical startup universe is scoped to THIS caller's own
# authorized analyses (approved decision -- no public scores-only
# exception), same as Rankings/Search/Startup Profile. Every filter is
# optional; Query(...) bounds below are the "invalid filters fail cleanly"
# layer (a 422 before any SQL ever runs), on top of app/database/db.py's
# own defensive clamping. Distinct from Rankings on purpose -- Rankings is
# "the canonical leaderboard" (unfiltered, full authorized population);
# Discovery is "help me find startups matching my criteria" (filtered,
# sorted, paginated). Both read the exact same authorized population;
# neither is a second definition of it. See discover_startups()'s own
# docstring in app/database/db.py.
# ---------------------------------------------------------------------------

@app.get("/discover", response_model=DiscoveryResponse)
def discover(
    current_user: AuthenticatedUser = RequireAuth,
    query: str | None = Query(None, max_length=200),
    industry: str | None = Query(None, max_length=200),
    stage: str | None = Query(None, max_length=200),
    business_model: str | None = Query(None, max_length=200),
    min_sps: float | None = Query(None, ge=0, le=100),
    max_sps: float | None = Query(None, ge=0, le=100),
    min_market: float | None = Query(None, ge=0, le=10),
    min_team: float | None = Query(None, ge=0, le=10),
    min_product: float | None = Query(None, ge=0, le=10),
    min_execution: float | None = Query(None, ge=0, le=10),
    min_traction: float | None = Query(None, ge=0, le=10),
    min_financial_health: float | None = Query(None, ge=0, le=10),
    sort: Literal["sps_desc", "sps_asc", "newest", "name_asc"] = "sps_desc",
    limit: int = Query(DEFAULT_DISCOVERY_LIMIT, ge=1, le=MAX_DISCOVERY_LIMIT),
    offset: int = Query(0, ge=0),
):
    filters = dict(
        query=query,
        industry=industry,
        stage=stage,
        business_model=business_model,
        min_sps=min_sps,
        max_sps=max_sps,
        min_market=min_market,
        min_team=min_team,
        min_product=min_product,
        min_execution=min_execution,
        min_traction=min_traction,
        min_financial_health=min_financial_health,
    )
    viewer_user_id = current_user.user_id
    viewer_is_admin = is_admin(current_user.user_id)

    try:
        results = discover_startups(
            viewer_user_id, viewer_is_admin, sort=sort, limit=limit, offset=offset, **filters
        )
        total = count_discover_startups(viewer_user_id, viewer_is_admin, **filters)
    except Exception as _exc:
        traceback.print_exc()
        capture_exception(_exc)
        raise HTTPException(
            status_code=500,
            detail="Discovery results could not be loaded. Please try again.",
        )

    return DiscoveryResponse(total=total, results=results)


@app.get("/discover/filter-options", response_model=DiscoveryFilterOptions)
def discover_filter_options(current_user: AuthenticatedUser = RequireAuth):
    try:
        return get_discovery_filter_options(current_user.user_id, is_admin(current_user.user_id))
    except Exception as _exc:
        traceback.print_exc()
        capture_exception(_exc)
        raise HTTPException(
            status_code=500,
            detail="Filter options could not be loaded. Please try again.",
        )


# ---------------------------------------------------------------------------
# Compare Startups V1. Portfolio Release Task 3B: now RequireAuth --
# comparing intelligence is scoped to startups this caller is authorized
# to see (approved decision -- no public scores-only exception). Reuses
# get_startups_for_comparison()'s canonical startup_id resolution (see its
# own docstring in app/database/db.py) -- this endpoint's own job is only
# input parsing/bounding and slimming the full methodology JSONB down to
# ComparisonStartup's fields. Passing explicit startup_id values that the
# caller is NOT authorized for is exactly the "explicit IDs must not
# bypass authorization" case -- get_startups_for_comparison() handles it
# by resolving those ids to nothing (same shape as an invalid id), not a
# distinguishing error.
# ---------------------------------------------------------------------------

def _build_comparison_pillar(pillar_key: str, methodology: dict) -> ComparisonPillar:
    pillar_data = methodology.get(pillar_key) or {}
    score_breakdown = pillar_data.get("score_breakdown") or {}
    subscores_data = score_breakdown.get("subscores") or []

    subscores = [
        ComparisonSubscore(
            name=subscore.get("name", ""),
            score=subscore.get("score"),
            weight=subscore.get("weight", 0.0),
            confidence=subscore.get("confidence", "Low"),
            evidence_status=subscore.get("evidence_status", "Observed"),
            rationale=subscore.get("rationale", ""),
            recommendations=subscore.get("recommendations") or [],
            missing_information=subscore.get("missing_information") or [],
        )
        for subscore in subscores_data
    ]

    return ComparisonPillar(
        pillar=pillar_key,
        score=pillar_data.get("score"),
        confidence=pillar_data.get("confidence", "Low"),
        evidence_coverage=score_breakdown.get("evidence_coverage", 0.0),
        summary=pillar_data.get("summary", ""),
        strengths=pillar_data.get("strengths") or [],
        weaknesses=pillar_data.get("weaknesses") or [],
        recommendations=pillar_data.get("recommendations") or [],
        subscores=subscores,
    )


def _build_comparison_startup(row: dict) -> ComparisonStartup:
    methodology = row["methodology"]
    context = methodology.get("context") or {}

    # Phase 10.9, Part 21: pure passthrough of the already-stored,
    # already-validated sps_v3 JSONB -- re-parsed through the Pydantic
    # model (not hand-picked fields) so a malformed/partial stored value
    # fails loudly rather than silently degrading. None whenever the
    # stored analysis has no sps_v3 at all, which SPSV3Assessment's own
    # `| None` type on the field already makes the correct default.
    sps_v3_raw = methodology.get("sps_v3")
    sps_v3 = SPSV3Assessment(**sps_v3_raw) if sps_v3_raw else None

    return ComparisonStartup(
        startup_id=row["startup_id"],
        company_name=context.get("company_name") or row["company_name"] or "",
        industry=context.get("industry", ""),
        company_stage=context.get("company_stage", ""),
        business_model=context.get("business_model", ""),
        latest_analysis_at=row["created_at"],
        overall_score=methodology.get("startup_intelligence_score"),
        market=_build_comparison_pillar("market", methodology),
        team=_build_comparison_pillar("team", methodology),
        product=_build_comparison_pillar("product", methodology),
        execution=_build_comparison_pillar("execution", methodology),
        traction=_build_comparison_pillar("traction", methodology),
        financial_health=_build_comparison_pillar("financial_health", methodology),
        sps_v3=sps_v3,
    )


@app.get("/compare", response_model=ComparisonResponse)
def compare(
    startups: str = Query(..., min_length=1, max_length=200),
    current_user: AuthenticatedUser = RequireAuth,
):
    # Deliberately permissive parsing -- a malformed/non-numeric token is
    # dropped, not a 422, matching Part 5's "invalid IDs fail gracefully".
    # Only "fewer than MIN_COMPARISON_STARTUPS well-formed ids" is a hard
    # rejection; everything else degrades to the most useful response it
    # can, with missing_startup_ids reporting what didn't resolve.
    raw_tokens = [token.strip() for token in startups.split(",") if token.strip()]

    parsed_ids: list[int] = []
    for token in raw_tokens:
        try:
            parsed_ids.append(int(token))
        except ValueError:
            continue

    deduped_ids = list(dict.fromkeys(parsed_ids))

    if len(deduped_ids) < MIN_COMPARISON_STARTUPS:
        raise HTTPException(
            status_code=400,
            detail=f"Provide at least {MIN_COMPARISON_STARTUPS} distinct startup IDs to compare.",
        )

    # Safely bounded, not hard-rejected: a shared/old link listing more
    # than the current max simply compares the first
    # MAX_COMPARISON_STARTUPS rather than erroring the whole request.
    bounded_ids = deduped_ids[:MAX_COMPARISON_STARTUPS]

    try:
        rows = get_startups_for_comparison(
            bounded_ids, current_user.user_id, is_admin(current_user.user_id)
        )
        resolved_ids = {row["startup_id"] for row in rows}
        missing_ids = [id_ for id_ in bounded_ids if id_ not in resolved_ids]
        comparison_startups = [_build_comparison_startup(row) for row in rows]
    except Exception as _exc:
        traceback.print_exc()
        capture_exception(_exc)
        raise HTTPException(
            status_code=500,
            detail="Comparison could not be loaded. Please try again.",
        )

    return ComparisonResponse(startups=comparison_startups, missing_startup_ids=missing_ids)


# Portfolio Release Task 3B: the four routes below are scoped to the
# caller's own authorized analyses (approved decision), same as
# Rankings/Discovery/Compare/Search above.
@app.get("/score-history/{company_name}")
def score_history(company_name: str, current_user: AuthenticatedUser = RequireAuth):
    return get_score_history(company_name, current_user.user_id, is_admin(current_user.user_id))

@app.get("/startup-trends/{company_name}")
def startup_trends(company_name: str, current_user: AuthenticatedUser = RequireAuth):
    return get_startup_trends(company_name, current_user.user_id, is_admin(current_user.user_id))

@app.get("/top-startups")
def top_startups(limit: int = 10, current_user: AuthenticatedUser = RequireAuth):
    return get_top_startups(current_user.user_id, is_admin(current_user.user_id), limit)

@app.get("/top-improving-startups")
def top_improving_startups(limit: int = 10, current_user: AuthenticatedUser = RequireAuth):
    return get_top_improving_startups(current_user.user_id, is_admin(current_user.user_id), limit)

# Portfolio Release Task 3B -- Secure Analysis Visibility. Was fully
# public (no auth at all); confirmed by the read-only audit as the
# headline leak vector (a signed-in user's uploaded pitch deck could end
# up quoted, verbatim, in methodology.*.score_breakdown.subscores[].evidence,
# returned here to anyone, no login required). Now RequireAuth, and
# get_startup_by_name() itself applies the visibility rule (submitter,
# approved member, or admin) before returning anything -- an unauthorized
# but signed-in caller gets the exact same 404 as "this company was never
# analyzed," never a distinguishing 403 that would confirm a private
# analysis exists.
@app.get(
    "/startup/{company_name}",
    response_model=StartupProfileResponse,
)
def get_startup_profile(company_name: str, current_user: AuthenticatedUser = RequireAuth):
    startup = get_startup_by_name(company_name, current_user.user_id, is_admin(current_user.user_id))

    if startup is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No canonical startup profile was found. "
                "The startup may need to be analyzed again."
            ),
        )

    return StartupProfileResponse(**startup)

@app.get("/startup/{company_name}/sps-history")
def get_startup_sps_history(company_name: str, current_user: AuthenticatedUser = RequireAuth):
    return get_sps_history(company_name, current_user.user_id, is_admin(current_user.user_id))


# ---------------------------------------------------------------------------
# Saved Startups / Watchlist -- Phase 1. All four endpoints require a
# valid Clerk-authenticated user (RequireAuth -- the same dependency the
# four paid analyze endpoints already use) and derive the acting user
# EXCLUSIVELY from current_user.user_id (the verified JWT's `sub` claim)
# -- never from a path/query/body parameter a caller could set to another
# user's id. There is deliberately no /users/{user_id}/saved-startups
# route: "the authenticated user" and "me" are the same thing everywhere
# below, which makes reading/saving/removing another user's list
# structurally impossible, not just policy-enforced.
#
# This is a watchlist/bookmark relationship only -- none of these ever
# touch startup_memberships, and saving a startup never implies ownership
# of it (see save_startup_for_user()'s own docstring in app/database/db.py
# and the SIE Accounts & Ownership architecture design).
#
# Public intelligence routes (GET /startup/{company_name} and everything
# above) are completely untouched by this section -- these are new,
# additive routes, not a change to how any existing route is protected.
# ---------------------------------------------------------------------------

@app.get("/me/saved-startups", response_model=list[SavedStartupEntry])
def list_my_saved_startups(
    current_user: AuthenticatedUser = RequireAuth,
):
    return get_saved_startups_for_user(current_user.user_id)


@app.get("/me/saved-startups/{startup_id}", response_model=SavedStartupStatus)
def get_my_saved_startup_status(
    startup_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    return SavedStartupStatus(
        saved=is_startup_saved_by_user(current_user.user_id, startup_id)
    )


@app.post("/me/saved-startups/{startup_id}", response_model=SavedStartupStatus)
def save_my_startup(
    startup_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    try:
        save_startup_for_user(current_user.user_id, startup_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Startup not found.")

    return SavedStartupStatus(saved=True)


@app.delete("/me/saved-startups/{startup_id}", response_model=SavedStartupStatus)
def unsave_my_startup(
    startup_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    unsave_startup_for_user(current_user.user_id, startup_id)
    return SavedStartupStatus(saved=False)


# ---------------------------------------------------------------------------
# Investor Workspace V1 (Phase 9). RequireAuth -- the same dependency
# Saved Startups already uses -- NOT RequireStartupMember: watching a
# startup as an investor is completely unrelated to being a verified
# startup member (Part 10). The acting user comes exclusively from
# current_user.user_id, exactly like every Saved Startups endpoint above;
# there is deliberately no /users/{user_id}/investor-workspace route.
#
# saved_startups remains the sole watchlist relationship -- this endpoint
# reads it (via get_watchlist_startups_for_user()) and deterministically
# diffs canonical intelligence (app/ai/investor_workspace.py); it writes
# nothing, so it can never affect SPS, methodology, Rankings, Discovery,
# VPS, or Fundraising Readiness.
# ---------------------------------------------------------------------------

@app.get("/investor/workspace", response_model=InvestorWorkspaceResponse)
def get_investor_workspace(
    current_user: AuthenticatedUser = RequireAuth,
):
    rows = get_watchlist_startups_for_user(current_user.user_id, is_admin(current_user.user_id))
    assessment = assess_investor_workspace(rows)

    return InvestorWorkspaceResponse(
        overview=InvestorOverviewOut(**assessment.overview.__dict__),
        watched_startups=[
            WatchedStartupOut(
                startup_id=w.startup_id,
                company_name=w.company_name,
                industry=w.industry,
                stage=w.stage,
                saved_at=w.saved_at,
                latest_analysis_at=w.latest_analysis_at,
                has_canonical_analysis=w.has_canonical_analysis,
                has_multiple_analyses=w.has_multiple_analyses,
                current_sps=w.current_sps,
                previous_sps=w.previous_sps,
                sps_delta=w.sps_delta,
                overall_confidence=w.overall_confidence,
                is_stale=w.is_stale,
                pillars=[PillarChangeOut(**p.__dict__) for p in w.pillars],
                attention_reasons=w.attention_reasons,
            )
            for w in assessment.watched_startups
        ],
        recent_changes=[RecentChangeOut(**c.__dict__) for c in assessment.recent_changes],
        attention_items=[AttentionItemOut(**a.__dict__) for a in assessment.attention_items],
    )


# ---------------------------------------------------------------------------
# Idea Lab / Venture Simulator V1. Every endpoint below requires
# RequireAuth and derives the acting user EXCLUSIVELY from
# current_user.user_id -- there is no /users/{user_id}/ventures route, so
# reading/editing/deleting another user's venture is structurally
# impossible, the same discipline as Saved Startups. modeled_ventures has
# no relationship to startups/analyses at all (see
# create_modeled_ventures_table()'s own docstring) -- nothing here can
# ever appear in Rankings, Discovery, or canonical Compare, and none of
# it creates a startup_membership or saved_startup.
#
# The Venture Potential Score (VPS) computed below is architecturally
# separate from SPS: compute_vps()/generate_guidance() (app/ai/
# vps_scoring.py, vps_guidance.py) never import from or call into
# app/ai/scoring.py, scoring_methodology.py, or investment_score.py, and
# never touch the analyses table. See those modules' own docstrings for
# the full reasoning.
# ---------------------------------------------------------------------------

def _build_model_result(assumptions: dict) -> dict:
    vps_result = compute_vps(assumptions)
    guidance = generate_guidance(assumptions, vps_result)
    return {**vps_result, **guidance}


# ---------------------------------------------------------------------------
# Phase 6.1 -- AI-Assisted Idea Setup. A stateless drafting endpoint: it
# reads nothing from and writes nothing to modeled_ventures (or any other
# table), never calls compute_vps()/_build_model_result(), and cannot
# create a Startup/Analysis -- there is no code path from here into
# save_analysis(), get_or_create_startup(), or any Rankings/Discovery
# query. Requires RequireAuth per the task's explicit instruction ("use
# the existing authenticated user boundary even though nothing is
# persisted") even though current_user is otherwise unused here -- this
# keeps the whole /ventures* surface consistently behind auth rather than
# carving out one public exception.
#
# Fails closed on every failure mode: StructureIdeaRequest's own
# min/max_length bounds reject empty/oversized input with a 422 before
# this function body ever runs; any LLM/parsing failure inside
# structure_idea() raises IdeaStructuringError, caught below and turned
# into one generic, safe 502 -- never the raw provider exception.
# ---------------------------------------------------------------------------

@app.post("/ventures/structure-idea", response_model=StructureIdeaResponse)
def structure_idea_endpoint(
    request: StructureIdeaRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    try:
        draft_dict = structure_idea(request.description)
        draft = VentureDraft(**draft_dict)
    except IdeaStructuringError:
        traceback.print_exc()
        raise HTTPException(
            status_code=502,
            detail="We couldn't structure that idea right now. Please try again.",
        )
    except Exception as _exc:
        traceback.print_exc()
        capture_exception(_exc)
        raise HTTPException(
            status_code=502,
            detail="We couldn't structure that idea right now. Please try again.",
        )

    return StructureIdeaResponse(draft=draft)


@app.post("/ventures", response_model=VentureResponse)
def create_venture(
    request: CreateVentureRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    assumptions_dict = request.assumptions.model_dump()
    model_result = _build_model_result(assumptions_dict)

    try:
        venture_id = create_modeled_venture(
            user_id=current_user.user_id,
            name=request.name,
            description=request.description,
            industry=request.industry,
            business_model=request.business_model,
            target_customer=request.target_customer,
            stage=request.stage,
            assumptions=assumptions_dict,
            model_result=model_result,
        )
    except Exception as _exc:
        traceback.print_exc()
        capture_exception(_exc)
        raise HTTPException(
            status_code=500,
            detail="Your venture could not be saved. Please try again.",
        )

    venture = get_modeled_venture_for_user(current_user.user_id, venture_id)

    # Phase 28 -- Product Analytics & Growth Measurement V1. THE one
    # server-side attribution decision point: `source` is only ever
    # trusted as "snapshot" (never any other client-supplied string) and
    # only when a real share_public_id accompanies it -- everything else
    # collapses to organic (None), regardless of what the request claims.
    # This is deliberately conservative: a client cannot fabricate a
    # "snapshot" attribution without also naming a real, resolvable
    # public_id a real recipient would have actually seen.
    attributed_source = "snapshot" if (request.source == "snapshot" and request.share_public_id) else None
    _log_event_safe(
        "venture_created",
        user_id=current_user.user_id,
        venture_id=venture_id,
        share_public_id=request.share_public_id if attributed_source else None,
        source=attributed_source,
    )

    return VentureResponse(**venture)


@app.get("/ventures", response_model=list[VentureSummary])
def list_ventures(current_user: AuthenticatedUser = RequireAuth):
    ventures = list_modeled_ventures_for_user(current_user.user_id)
    # Phase 34E: one bulk query for every venture's active question at
    # once -- never one call per card.
    active_questions = list_active_questions_for_user(current_user.user_id)

    return [
        VentureSummary(
            id=venture["id"],
            name=venture["name"],
            stage=venture["stage"],
            vps=(venture["model_result"] or {}).get("vps"),
            current_question=active_questions.get(venture["id"]),
            updated_at=venture["updated_at"],
        )
        for venture in ventures
    ]


@app.get("/ventures/{venture_id}", response_model=VentureResponse)
def get_venture(
    venture_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    venture = get_modeled_venture_for_user(current_user.user_id, venture_id)

    if venture is None:
        # Deliberately the same 404 whether the id doesn't exist at all or
        # belongs to a different user -- see
        # get_modeled_venture_for_user()'s own docstring.
        raise HTTPException(status_code=404, detail="Venture not found.")

    return VentureResponse(**venture)


@app.put("/ventures/{venture_id}", response_model=VentureResponse)
def update_venture(
    venture_id: int,
    request: UpdateVentureRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    # Founder Progress / Venture History V1: the "before" snapshot must be
    # read BEFORE the UPDATE runs -- this is the one and only place a
    # venture's prior assumptions/model_result are ever captured, since
    # modeled_ventures itself only ever stores current state (Part 5's own
    # investigation finding). Ownership is still enforced structurally by
    # update_modeled_venture_for_user()'s own WHERE clause below, not by
    # this read succeeding -- a venture that doesn't belong to this user
    # returns None here and 404s exactly as before this phase.
    previous = get_modeled_venture_for_user(current_user.user_id, venture_id)

    assumptions_dict = request.assumptions.model_dump()
    model_result = _build_model_result(assumptions_dict)

    updated = update_modeled_venture_for_user(
        user_id=current_user.user_id,
        venture_id=venture_id,
        name=request.name,
        description=request.description,
        industry=request.industry,
        business_model=request.business_model,
        target_customer=request.target_customer,
        stage=request.stage,
        assumptions=assumptions_dict,
        model_result=model_result,
    )

    if not updated:
        raise HTTPException(status_code=404, detail="Venture not found.")

    # THE VPS FIREWALL, restated: this history write happens exclusively
    # inside the SAME PUT this venture's assumptions were already,
    # independently, explicitly saved through -- it never runs from any
    # mission/learning endpoint, and it never itself computes or changes
    # a score (model_result above was already computed regardless of
    # whether history recording happens at all). Only written when the
    # assumptions ACTUALLY changed -- a no-op "Save" (e.g. clicking Save
    # with no edits) must not manufacture a history entry.
    if previous is not None and previous.get("assumptions") != assumptions_dict:
        create_venture_model_update(
            venture_id=venture_id,
            user_id=current_user.user_id,
            before_vps=(previous.get("model_result") or {}).get("vps"),
            after_vps=(model_result or {}).get("vps"),
            before_categories=(previous.get("model_result") or {}).get("categories", []),
            after_categories=(model_result or {}).get("categories", []),
            before_assumptions=previous.get("assumptions") or {},
            after_assumptions=assumptions_dict,
            related_mission_id=request.related_mission_id,
        )
        # Phase 28, Part 3/4: fires in the EXACT SAME branch that just
        # decided a real venture_model_updates history row is warranted --
        # never a second, possibly-inconsistent definition of "the model
        # actually changed." This is also why a pure rename (Phase 26,
        # Part 15) never fires this event: a rename sends identical
        # assumptions, so this whole branch (history AND analytics) is
        # skipped, for the same reason. Covers Simulate-Apply and the
        # manual assumption editor identically -- both reach this exact
        # code path through the same PUT, and this phase deliberately
        # does not distinguish them (see the doc's own "events rejected/
        # deferred" section).
        before_vps = (previous.get("model_result") or {}).get("vps")
        after_vps = (model_result or {}).get("vps")
        if before_vps is None or after_vps is None:
            vps_delta_bucket = "unknown"
        elif after_vps > before_vps + 0.05:
            vps_delta_bucket = "increased"
        elif after_vps < before_vps - 0.05:
            vps_delta_bucket = "decreased"
        else:
            vps_delta_bucket = "unchanged"
        _log_event_safe(
            "venture_model_updated",
            user_id=current_user.user_id,
            venture_id=venture_id,
            metadata={"vps_delta_bucket": vps_delta_bucket},
        )

    venture = get_modeled_venture_for_user(current_user.user_id, venture_id)
    return VentureResponse(**venture)


@app.delete("/ventures/{venture_id}")
def delete_venture(
    venture_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    deleted = delete_modeled_venture_for_user(current_user.user_id, venture_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Venture not found.")

    return {"deleted": True}


# ---------------------------------------------------------------------------
# Phase 27 -- Shareable Venture Snapshot V1.
#
# THE FIREWALL, restated exactly as every prior phase's own capture/model-
# update firewall was: nothing in this section calls compute_vps(),
# _build_model_result(), create_venture_model_update(), create_venture_mission(),
# or update_modeled_venture_for_user(). Enabling/disabling/previewing a
# snapshot reads and writes ONLY the four share_* columns added by
# add_venture_share_columns() -- it can never change VPS, never writes
# venture_model_updates history, never creates an Action, never touches
# SPS (an entirely separate table/pipeline this section has no import of).
# ---------------------------------------------------------------------------

def _build_venture_snapshot(venture: dict, show_vps: bool, show_validation: bool) -> VentureSnapshotResponse:
    """
    THE single allowlisted DTO builder -- used by BOTH the founder's own
    preview (GET /ventures/{id}/share) and the public endpoint
    (GET /ventures/share/{public_id}). One function, one place the
    public/private shape can ever be defined, so a preview can never
    honestly diverge from what a recipient actually sees (Part 16).

    `venture` here is deliberately whatever get_venture_by_share_public_id()
    or get_modeled_venture_for_user() returned -- both include the full
    `assumptions` dict, but this function reads only the specific,
    named sub-fields it builds evidence strings from. It never returns
    `assumptions` itself, never reads/returns `description`, and never
    reads/returns economics.expected_gross_margin_pct, gtm.expected_cac,
    or capital.* -- those fields are structurally never touched here,
    not merely omitted from the output.
    """
    assumptions = venture.get("assumptions") or {}
    problem_solution = assumptions.get("problem_solution") or {}
    validation = assumptions.get("validation") or {}
    economics = assumptions.get("economics") or {}
    model_result = venture.get("model_result") or {}

    evidence: list[str] = []
    if show_validation:
        interviews = validation.get("customer_interviews")
        if interviews:
            evidence.append(f"{interviews:,} customer conversation{'s' if interviews != 1 else ''} reported")

        waitlist = validation.get("waitlist_signups")
        if waitlist:
            evidence.append(f"{waitlist:,} waitlist signup{'s' if waitlist != 1 else ''}")

        paying = validation.get("paying_customers")
        if paying:
            evidence.append(f"{paying:,} paying customer{'s' if paying != 1 else ''} reported")

        price_point = economics.get("price_point")
        if price_point:
            evidence.append(f"${price_point:,.0f}/month pricing")

        revenue = validation.get("monthly_revenue")
        if revenue:
            evidence.append(f"${revenue:,.0f}/mo modeled revenue")

        retention = validation.get("retention_pct")
        if retention:
            evidence.append(f"{retention:g}% retention reported")

    next_milestones = model_result.get("next_milestones") or []
    current_frontier = next_milestones[0] if next_milestones else None

    vps_value = model_result.get("vps") if show_vps else None
    vps_categories = None
    if show_vps:
        vps_categories = [
            VentureSnapshotCategory(key=c["key"], label=c["label"], score=c.get("score"))
            for c in (model_result.get("categories") or [])
        ]

    return VentureSnapshotResponse(
        name=venture["name"],
        stage=venture.get("stage"),
        problem_statement=problem_solution.get("problem_statement"),
        solution_description=problem_solution.get("solution_description"),
        target_customer=venture.get("target_customer"),
        evidence=evidence,
        current_frontier=current_frontier,
        vps=vps_value,
        vps_categories=vps_categories,
        updated_at=venture["updated_at"],
    )


@app.get("/ventures/{venture_id}/share", response_model=VentureShareSettings)
def get_venture_share(
    venture_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    settings = get_venture_share_settings_for_owner(current_user.user_id, venture_id)

    if settings is None:
        raise HTTPException(status_code=404, detail="Venture not found.")

    return VentureShareSettings(
        enabled=settings["share_enabled"],
        public_id=settings["share_public_id"],
        show_vps=settings["share_show_vps"],
        show_validation=settings["share_show_validation"],
    )


@app.get("/ventures/{venture_id}/share/preview", response_model=VentureSnapshotResponse)
def preview_venture_share(
    venture_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    """
    The founder's own preview -- rendered with the SAME DTO builder the
    public endpoint uses below, so "what I'm about to share" can never
    look safer than what a recipient actually receives (Part 16). Reads
    the venture's CURRENT share_show_vps/share_show_validation toggles,
    regardless of whether sharing is currently enabled -- a founder must
    be able to preview before ever turning sharing on.
    """
    venture = _require_owned_venture(current_user, venture_id)
    settings = get_venture_share_settings_for_owner(current_user.user_id, venture_id)

    return _build_venture_snapshot(
        venture,
        show_vps=bool(settings and settings["share_show_vps"]),
        show_validation=bool(settings is None or settings["share_show_validation"]),
    )


@app.put("/ventures/{venture_id}/share", response_model=VentureShareSettings)
def update_venture_share(
    venture_id: int,
    request: UpdateVentureShareRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    # Phase 28, Part 3/18: read BEFORE writing, same pattern
    # venture_model_updated's own before/after comparison above already
    # uses -- this is what lets the event fire ONLY on a genuine
    # private->public (or public->private) TRANSITION, never on a
    # double-submit of the same state (Part 18's own explicit "enable
    # sharing button double-submit... should not create duplicate
    # logical activation events").
    previous = get_venture_share_settings_for_owner(current_user.user_id, venture_id)

    updated = update_venture_share_settings_for_owner(
        user_id=current_user.user_id,
        venture_id=venture_id,
        enabled=request.enabled,
        show_vps=request.show_vps,
        show_validation=request.show_validation,
    )

    if updated is None:
        raise HTTPException(status_code=404, detail="Venture not found.")

    was_enabled = bool(previous and previous["share_enabled"])
    is_enabled = bool(updated["share_enabled"])
    if is_enabled and not was_enabled:
        _log_event_safe(
            "snapshot_enabled",
            user_id=current_user.user_id,
            venture_id=venture_id,
            share_public_id=updated["share_public_id"],
        )
    elif was_enabled and not is_enabled:
        _log_event_safe(
            "snapshot_disabled",
            user_id=current_user.user_id,
            venture_id=venture_id,
            share_public_id=updated["share_public_id"],
        )

    return VentureShareSettings(
        enabled=updated["share_enabled"],
        public_id=updated["share_public_id"],
        show_vps=updated["share_show_vps"],
        show_validation=updated["share_show_validation"],
    )


@app.get("/ventures/share/{public_id}", response_model=VentureSnapshotResponse)
def get_public_venture_snapshot(public_id: str):
    """
    THE public route. No auth dependency at all -- matches this file's
    own existing public-endpoint precedent (get_startup_profile,
    startup_trends). get_venture_by_share_public_id() already filters on
    share_enabled=TRUE in SQL, so a disabled or never-shared id returns
    None here -- indistinguishable, by design, from a malformed/unknown
    one (never leaks which case it was).
    """
    venture = get_venture_by_share_public_id(public_id)

    if venture is None:
        raise HTTPException(status_code=404, detail="This venture snapshot is not available.")

    # Phase 28, Part 3/4: fires only on a REAL, successfully-resolved
    # public view -- a 404 (disabled/unknown id) logs nothing at all, so
    # "Public Snapshot Views" can never be inflated by scraping/guessing
    # attempts. No user_id (this visitor is anonymous, by design -- Part
    # 6: "do not fingerprint users"); venture_id + share_public_id are
    # enough to attribute the view to the right venture for reporting
    # without tracking who the visitor is.
    _log_event_safe("snapshot_viewed_publicly", venture_id=venture["id"], share_public_id=public_id)

    return _build_venture_snapshot(
        venture,
        show_vps=bool(venture["share_show_vps"]),
        show_validation=bool(venture["share_show_validation"]),
    )


# Phase 28, Part 4/5. Two narrow, purpose-built endpoints -- deliberately
# NOT one generic "log any client event" endpoint (that would be exactly
# the "arbitrary event explorer" the directive forbids, and a real abuse
# surface on the public one). Each accepts an EMPTY body: the event name
# and every field are decided entirely server-side from the URL path and
# auth context, never from anything the client sends.
@app.post("/ventures/{venture_id}/share/link-copied")
def log_snapshot_link_copied(
    venture_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    _log_event_safe("snapshot_link_copied", user_id=current_user.user_id, venture_id=venture_id)
    return {"logged": True}


@app.post("/ventures/share/{public_id}/cta-clicked")
def log_snapshot_cta_clicked(public_id: str):
    """
    Public, unauthenticated -- the recipient clicking "Model your own
    venture" has no Clerk session. Validated against a REAL, currently-
    enabled snapshot before logging (the same lookup the public view
    itself uses) so this can't be used to write arbitrary garbage rows
    for nonexistent ids; beyond that one check, no rate-limiting/abuse
    infrastructure was built (out of this phase's explicit scope).
    """
    venture = get_venture_by_share_public_id(public_id)
    if venture is not None:
        _log_event_safe("snapshot_cta_clicked", venture_id=venture["id"], share_public_id=public_id)
    return {"logged": venture is not None}


@app.get("/admin/analytics")
def get_admin_analytics_report(
    window_days: int = 7,
    current_user: AuthenticatedUser = RequireAdmin,
):
    """
    Phase 28, Part 13. The smallest safe internal reporting surface --
    reuses the EXACT SAME RequireAdmin dependency this codebase already
    uses for claim-approval endpoints (app/auth.py, Phase 7.1A). No new
    RBAC/role system, no new admin table, no admin flag anywhere on
    `users`. window_days is clamped to a sane range so this can't be
    abused into an unbounded full-table scan.
    """
    clamped_window = max(1, min(window_days, 365))
    return get_full_analytics_report(clamped_window)


@app.post("/ventures/scenario-compare", response_model=ScenarioCompareResponse)
def compare_venture_scenarios(
    request: ScenarioCompareRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    """
    Part 11: current vs. modified scenario -- stateless (both assumption
    sets come from the request body; nothing is read from or written to
    modeled_ventures here), so trying a scenario never overwrites the
    venture's actually-saved assumptions. Requires auth only because it's
    part of the private Idea Lab surface, not because it reads any
    per-user data. Deliberately a distinct endpoint from GET /compare --
    it never touches startups/analyses/canonical Startup identity, and a
    modeled venture can never be passed to /compare's startup_id-based
    contract.
    """
    current_result = _build_model_result(request.current_assumptions.model_dump())
    modified_result = _build_model_result(request.modified_assumptions.model_dump())

    return ScenarioCompareResponse(
        current=VPSResult(**current_result),
        modified=VPSResult(**modified_result),
    )


# ---------------------------------------------------------------------------
# Phase 10.7 -- Founder Missions V1.
#
# THE VPS FIREWALL: no function in this section calls
# _build_model_result()/compute_vps(), and none writes to
# modeled_ventures.assumptions or modeled_ventures.model_result. A
# mission's status (active/completed/dismissed) and its learning_summary
# have no code path to a score -- see venture_missions's own table
# docstring in app/database/db.py for the full reasoning. The ONLY way a
# score changes is the pre-existing PUT /ventures/{venture_id} above,
# unchanged by this phase.
#
# AUTHORIZATION: every endpoint below first calls
# get_modeled_venture_for_user(current_user.user_id, venture_id) and 404s
# if it returns None -- the exact same "doesn't exist" and "belongs to
# someone else" collapse into one response every other /ventures/{id}
# endpoint already uses (see get_modeled_venture_for_user()'s own
# docstring), so a cross-user probe can never distinguish "no such
# venture" from "not yours". The mission-table functions themselves
# additionally re-scope by owner in their own SQL (defense in depth, not
# the only check).
# ---------------------------------------------------------------------------

def _require_owned_venture(current_user: AuthenticatedUser, venture_id: int):
    venture = get_modeled_venture_for_user(current_user.user_id, venture_id)

    if venture is None:
        raise HTTPException(status_code=404, detail="Venture not found.")

    return venture


# Phase 28, Part 19: BELT AND SUSPENDERS. log_product_event() already
# catches its own INSERT failures internally (see its own docstring in
# app/database/db.py) -- this wraps every call site here too, so that
# even a failure mode INSIDE this codebase's own analytics layer (a
# raised ValueError from an unrecognized event name, an unexpected
# exception before the INSERT is even attempted) can never propagate
# into a 500 response for a real founder action. Every one of the 9 call
# sites in this file goes through this wrapper, never log_product_event()
# directly.
def _log_event_safe(event_name: str, **kwargs) -> None:
    try:
        log_product_event(event_name, **kwargs)
    except Exception as error:
        print(f"product event logging failed for '{event_name}' (call-site guard)", error)


@app.get("/ventures/{venture_id}/missions", response_model=list[VentureMissionResponse])
def list_venture_missions(
    venture_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)

    missions = list_venture_missions_for_owner(current_user.user_id, venture_id)
    return [VentureMissionResponse(**mission) for mission in missions]


@app.post("/ventures/{venture_id}/missions", response_model=VentureMissionResponse)
def create_mission(
    venture_id: int,
    request: CreateMissionRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)

    mission = create_venture_mission(
        venture_id=venture_id,
        user_id=current_user.user_id,
        title=request.title,
        description=request.description,
        mission_type=request.mission_type,
        related_category=request.related_category,
        source=request.source,
        resource_ref=request.resource_ref,
        question_text=request.question_text,
        why_it_matters=request.why_it_matters,
        idempotency_key=request.idempotency_key,
    )
    # Phase 28, Part 3: fires only after a real mission row is persisted --
    # never on the founder merely opening "Create your own action" or a
    # NextMoves suggestion rendering. `mission_source` mirrors this
    # mission's own already-safe, closed `source` enum (vps_guidance /
    # founder_created / pitch_deck_coach) -- never its title/description.
    _log_event_safe(
        "action_created",
        user_id=current_user.user_id,
        venture_id=venture_id,
        metadata={"mission_source": mission["source"]},
    )
    return VentureMissionResponse(**mission)


@app.patch("/ventures/{venture_id}/missions/{mission_id}/status", response_model=VentureMissionResponse)
def update_mission_status(
    venture_id: int,
    mission_id: int,
    request: UpdateMissionStatusRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)

    mission = update_venture_mission_status_for_owner(
        user_id=current_user.user_id,
        venture_id=venture_id,
        mission_id=mission_id,
        new_status=request.status,
    )

    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found.")

    # Phase 28, Part 3/18: fires ONLY on the "completed" transition, never
    # "dismissed" -- a real, deliberate building outcome. The UI's own
    # existing flow hides the complete affordance once a mission is
    # already completed (no redundant call in normal use), so this
    # doesn't re-check prior status server-side (Part 18: "do not
    # overengineer global event deduplication -- handle obvious cases at
    # event-source level").
    if request.status == "completed":
        _log_event_safe("action_completed", user_id=current_user.user_id, venture_id=venture_id)

    return VentureMissionResponse(**mission)


@app.post("/ventures/{venture_id}/missions/{mission_id}/learning", response_model=VentureMissionResponse)
def record_mission_learning(
    venture_id: int,
    mission_id: int,
    request: RecordMissionLearningRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)

    mission = record_venture_mission_learning_for_owner(
        user_id=current_user.user_id,
        venture_id=venture_id,
        mission_id=mission_id,
        learning_summary=request.learning_summary,
    )

    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found.")

    # Phase 28, Part 2: a genuine, distinct building behavior -- an
    # ORDINARY mission's own reflection step, never fired for a capture
    # (captures never call this endpoint at all; see
    # capture_venture_observation()'s own atomic-INSERT design, which
    # sets learning_recorded_at directly without going through this code
    # path -- so this event and capture_recorded can never double-fire
    # for the same real founder action).
    _log_event_safe("learning_recorded", user_id=current_user.user_id, venture_id=venture_id)

    return VentureMissionResponse(**mission)


# ---------------------------------------------------------------------------
# Phase 34D -- SIE Build Intelligence Loop V1.
#
# QUESTION -> TEST -> RESULT -> EVIDENCE -> INTERPRETATION -> RECOMMENDATION
# -> DECISION -> OUTCOME. "Start a test" reuses POST .../missions above
# (extended with question_text/why_it_matters); "record a result" reuses
# POST .../missions/{id}/learning above unchanged. This section adds
# exactly the two genuinely new resources the accepted architecture
# calls for (docs/product/SIE_BUILD_INTELLIGENCE_ARCHITECTURE_V1.md §D):
# Evidence and Decision -- plus one small read-only endpoint that answers
# "what matters now" without touching VentureResponse's existing,
# widely-used shape at all.
# ---------------------------------------------------------------------------

@app.get("/ventures/{venture_id}/recommendation", response_model=BuildRecommendationResponse)
def get_venture_recommendation(
    venture_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    venture = _require_owned_venture(current_user, venture_id)

    missions = list_venture_missions_for_owner(current_user.user_id, venture_id)
    active_mission = next(
        (m for m in missions if m["status"] == "active" and m.get("question_text")),
        None,
    )
    evidence_rows = list_venture_evidence_for_owner(current_user.user_id, venture_id)
    # Superseded evidence is corrected, not deleted (§18) -- but a
    # correction means the ORIGINAL row is no longer the founder's
    # current understanding, so the recommendation engine reasons only
    # over the still-current ones.
    current_evidence = [e for e in evidence_rows if e["superseded_by_id"] is None]

    state = build_intelligence_state(
        venture_name=venture["name"],
        model_result=venture.get("model_result"),
        active_mission=active_mission,
        evidence_rows=current_evidence,
        # Phase 34F, Section 7: lets the fallback recommendation respect
        # the one prerequisite it must know before recommending customer
        # interviews -- whether a target customer has been described yet.
        target_customer=venture.get("target_customer"),
    )
    # Phase 34G §10-13: computed from the SAME evidence/mission rows
    # already fetched above -- no second round-trip, no new AI call.
    completed_missions = [m for m in missions if m.get("completed_at") is not None]
    decisions = list_venture_decisions_for_owner(current_user.user_id, venture_id)
    latest_decision = decisions[-1] if decisions else None
    company_intelligence = build_company_intelligence_summary(
        evidence_rows=current_evidence,
        completed_missions=completed_missions,
        latest_decision=latest_decision,
        # Phase 34G-A §9: the identical gate the recommendation itself
        # checks first, so "still figuring out" agrees with it by
        # construction rather than by convention.
        target_customer=venture.get("target_customer"),
    )
    return BuildRecommendationResponse(
        current_question=CurrentQuestion(**state["current_question"]) if state["current_question"] else None,
        recommendation=BuildRecommendation(**state["recommendation"]) if state["recommendation"] else None,
        company_intelligence=CompanyIntelligenceSummary(**company_intelligence),
    )


@app.get("/ventures/{venture_id}/evidence", response_model=list[VentureEvidenceResponse])
def list_venture_evidence(
    venture_id: int,
    mission_id: int | None = None,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    evidence = list_venture_evidence_for_owner(current_user.user_id, venture_id, related_mission_id=mission_id)
    return [VentureEvidenceResponse(**row) for row in evidence]


# Phase 34D §6/§19: founder confirmation is mandatory -- this endpoint is
# the ONLY way a venture_evidence row is ever created, and it always
# writes founder_confirmed=True (see create_venture_evidence()'s own
# docstring in app/database/db.py). There is no code path where
# captureSignals.ts's client-side extraction alone, without this explicit
# call, becomes durable evidence.
@app.post("/ventures/{venture_id}/evidence", response_model=VentureEvidenceResponse)
def create_evidence(
    venture_id: int,
    request: CreateEvidenceRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)

    # Ownership, restated for the two optional cross-references this
    # request can carry (§17: "evidence cannot attach to a mission from
    # another venture" / "...to another venture's decision") -- both are
    # re-scoped through THIS venture_id, never trusted as bare ids.
    if request.related_mission_id is not None:
        missions = list_venture_missions_for_owner(current_user.user_id, venture_id)
        if not any(m["id"] == request.related_mission_id for m in missions):
            raise HTTPException(status_code=404, detail="Mission not found for this venture.")
    if request.related_decision_id is not None:
        decisions = list_venture_decisions_for_owner(current_user.user_id, venture_id)
        if not any(d["id"] == request.related_decision_id for d in decisions):
            raise HTTPException(status_code=404, detail="Decision not found for this venture.")

    evidence = create_venture_evidence(
        venture_id=venture_id,
        user_id=current_user.user_id,
        evidence_type=request.evidence_type,
        statement=request.statement,
        provenance=request.provenance,
        related_mission_id=request.related_mission_id,
        related_decision_id=request.related_decision_id,
        source_quote=request.source_quote,
        structured_field_path=request.structured_field_path,
        structured_value=request.structured_value,
        relationship=request.relationship,
        occurred_at=request.occurred_at,
        idempotency_key=request.idempotency_key,
    )

    # Once evidence is confirmed for a question, (re)generate its
    # interpretation from the FULL current evidence set for that
    # mission -- never just the newest row -- per
    # generate_interpretation()'s own docstring.
    if request.related_mission_id is not None:
        all_evidence_for_mission = [
            e for e in list_venture_evidence_for_owner(current_user.user_id, venture_id, related_mission_id=request.related_mission_id)
            if e["superseded_by_id"] is None
        ]
        missions = list_venture_missions_for_owner(current_user.user_id, venture_id)
        mission = next((m for m in missions if m["id"] == request.related_mission_id), None)
        if mission is not None:
            interpretation = generate_interpretation(mission.get("question_text") or mission["title"], all_evidence_for_mission)
            set_venture_mission_interpretation_for_owner(
                user_id=current_user.user_id,
                venture_id=venture_id,
                mission_id=request.related_mission_id,
                interpretation_summary=interpretation["summary"],
                interpretation_limitations=interpretation["limitations"],
            )

    _log_event_safe(
        "evidence_confirmed",
        user_id=current_user.user_id,
        venture_id=venture_id,
        metadata={"evidence_type": evidence["evidence_type"], "provenance": evidence["provenance"]},
    )

    return VentureEvidenceResponse(**evidence)


# Phase 34G-A §3/§6 -- Intelligence Resolution + Learning Integrity
# Hardening. The minimum founder-facing mechanism that distinguishes
# EXISTS from CURRENTLY DECISION-DOMINANT: marks one specific
# contradicting/mixed evidence row (surfaced to the founder as
# `BuildRecommendation.blocking_evidence`) as no longer the current
# picture, in the founder's own words. Never edits or deletes the
# original row -- see resolve_venture_evidence_for_owner()'s own
# docstring. This is NOT a general "correct any evidence" endpoint; it is
# scoped to exactly the resolution gesture the directive asked for.
@app.post("/ventures/{venture_id}/evidence/{evidence_id}/resolve", response_model=VentureEvidenceResponse)
def resolve_evidence(
    venture_id: int,
    evidence_id: int,
    request: ResolveEvidenceRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    new_row = resolve_venture_evidence_for_owner(
        user_id=current_user.user_id,
        venture_id=venture_id,
        evidence_id=evidence_id,
        resolution_note=request.resolution_note,
    )
    if new_row is None:
        raise HTTPException(status_code=404, detail="Evidence not found, or it has already been resolved.")

    _log_event_safe(
        "evidence_resolved",
        user_id=current_user.user_id,
        venture_id=venture_id,
        metadata={"resolved_evidence_id": evidence_id},
    )

    return VentureEvidenceResponse(**new_row)


# ---------------------------------------------------------------------------
# Phase 35B -- Financial State Persistence + Runway Engine V1. See
# docs/product/SIE_FINANCIAL_DECISION_ENGINE_V2.md.
#
# Access doctrine (§2 of the directive): NO gate here on stage,
# verification, graduation, evidence quantity, or SPS -- _require_owned_venture()
# is the exact same, and ONLY, authorization check every other Build
# endpoint already uses. Any founder who owns the venture can read/write
# its financials, at any stage, unconditionally.
# ---------------------------------------------------------------------------

def _hire_plan_response(row: dict) -> HirePlanResponse:
    return HirePlanResponse(
        **row,
        computed_monthly_cost_cents=compute_hire_monthly_cost_cents(row),
        computed_annual_cost_cents=compute_hire_annual_cost_cents(row),
    )


def _financial_plan_response(row: dict) -> FinancialPlanResponse:
    return FinancialPlanResponse(**row)


def _all_plan_items_for_projection(all_hires: list[dict], all_financial_plans: list[dict]) -> list[dict]:
    """The one place hire items and revenue/expense items are combined
    into a single list for the projection engine (§8/§9 of the Phase 35D
    directive) -- the engine itself never distinguishes their origin,
    only their `kind`."""
    return hire_plan_items_for_projection(all_hires) + financial_plan_items_for_projection(all_financial_plans)


def _build_financials_response(user_id: str, venture_id: int, snapshot: dict | None) -> VentureFinancialsResponse:
    # Phase 35C/35D: plans and the with-plan projection are computed
    # regardless of whether a snapshot exists -- with no snapshot,
    # the projection engine has nothing to project against either
    # (project_monthly_cash_flow returns [] the same way §35B's own
    # empty state already does), so this stays honest by construction,
    # not by a separate check.
    all_hires = list_venture_hire_plans_for_owner(user_id, venture_id)
    all_financial_plans = list_venture_financial_plans_for_owner(user_id, venture_id)
    hire_plans = [_hire_plan_response(h) for h in all_hires]
    financial_plans = [_financial_plan_response(p) for p in all_financial_plans]

    if snapshot is None:
        return VentureFinancialsResponse(
            latest_snapshot=None, derived=None, projection=[],
            hire_plans=hire_plans, financial_plans=financial_plans,
            projection_with_plan=[], pending_reconciliation=[],
        )

    derived = compute_derived_metrics(snapshot)
    projection = project_monthly_cash_flow(snapshot, snapshot["as_of_date"])
    plan_items = _all_plan_items_for_projection(all_hires, all_financial_plans)
    projection_with_plan = project_monthly_cash_flow(snapshot, snapshot["as_of_date"], plan_items=plan_items)

    pending = list_pending_reconciliation_for_owner(user_id, venture_id, snapshot["id"], snapshot["as_of_date"])
    pending_reconciliation = [
        ReconciliationItem(
            plan_kind="hire", plan_id=h["id"], label=h["role"],
            monthly_amount_cents=compute_hire_monthly_cost_cents(h), start_date=h["start_date"],
        )
        for h in pending["hire_plans"]
    ] + [
        ReconciliationItem(
            plan_kind="financial", plan_id=p["id"], label=p["label"],
            monthly_amount_cents=p["amount_cents"] if p["plan_type"] == "expense_change" else None,
            start_date=p["start_date"],
        )
        for p in pending["financial_plans"]
    ]

    return VentureFinancialsResponse(
        latest_snapshot=FinancialSnapshotResponse(**snapshot),
        derived=DerivedFinancialMetrics(**derived),
        projection=[ProjectedMonth(**month) for month in projection],
        hire_plans=hire_plans,
        financial_plans=financial_plans,
        projection_with_plan=[ProjectedMonthWithPlan(**month) for month in projection_with_plan],
        pending_reconciliation=pending_reconciliation,
    )


@app.get("/ventures/{venture_id}/financials", response_model=VentureFinancialsResponse)
def get_venture_financials(
    venture_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    snapshot = get_latest_venture_financial_snapshot_for_owner(current_user.user_id, venture_id)
    return _build_financials_response(current_user.user_id, venture_id, snapshot)


# Always creates a NEW snapshot row (§12: append-only, never overwrites a
# prior one) -- this is the ONLY write path into venture_financial_snapshots
# (see create_venture_financial_snapshot()'s own docstring), which is what
# lets every field's provenance be FOUNDER_ENTERED by construction, with
# no separate provenance column needed yet.
@app.post("/ventures/{venture_id}/financials", response_model=VentureFinancialsResponse)
def create_venture_financials_snapshot(
    venture_id: int,
    request: CreateFinancialSnapshotRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    snapshot = create_venture_financial_snapshot(
        venture_id=venture_id,
        user_id=current_user.user_id,
        as_of_date=request.as_of_date,
        cash_balance_cents=request.cash_balance_cents,
        monthly_recurring_revenue_cents=request.monthly_recurring_revenue_cents,
        monthly_non_recurring_revenue_cents=request.monthly_non_recurring_revenue_cents,
        payroll_cents=request.payroll_cents,
        contractors_cents=request.contractors_cents,
        software_cents=request.software_cents,
        marketing_cents=request.marketing_cents,
        rent_cents=request.rent_cents,
        professional_services_cents=request.professional_services_cents,
        other_expenses_cents=request.other_expenses_cents,
        idempotency_key=request.idempotency_key,
    )

    _log_event_safe(
        "financial_snapshot_recorded",
        user_id=current_user.user_id,
        venture_id=venture_id,
        metadata={"as_of_date": str(request.as_of_date)},
    )

    # Re-fetch the LATEST snapshot rather than trivially returning the one
    # just inserted: as_of_date is founder-chosen and could, in principle,
    # be backdated relative to an existing later snapshot -- "current
    # state" must always mean the same thing GET returns, computed the
    # same way, never two different definitions of "latest."
    latest = get_latest_venture_financial_snapshot_for_owner(current_user.user_id, venture_id)
    return _build_financials_response(current_user.user_id, venture_id, latest)


@app.get("/ventures/{venture_id}/financials/history", response_model=FinancialHistoryResponse)
def get_venture_financials_history(
    venture_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    snapshots = list_venture_financial_snapshots_for_owner(current_user.user_id, venture_id)
    return FinancialHistoryResponse(snapshots=[FinancialSnapshotResponse(**s) for s in snapshots])


# ---------------------------------------------------------------------------
# Phase 35C -- Hiring + Operating Plan Engine V1. See
# docs/product/SIE_FINANCIAL_DECISION_ENGINE_V2.md.
#
# Same access doctrine as 35B: _require_owned_venture() only, no stage/
# verification/graduation gate. A hire PLAN never touches
# venture_financial_snapshots -- ACTUAL and PLAN remain permanently
# separate tables, per §1 of this phase's own directive.
# ---------------------------------------------------------------------------


def _create_hire_request_to_row(request: CreateHirePlanRequest) -> dict:
    """The shape compute_hire_monthly_cost_cents()/hire_to_plan_item()
    expect -- a plain dict mirroring a DB row's own field names, whether
    this hire is persisted yet or not (used identically by both the real
    create endpoint and the never-persisted preview endpoint)."""
    return {
        "employment_type": request.employment_type,
        "annual_salary_cents": request.annual_salary_cents,
        "burden_percent": request.burden_percent,
        "monthly_cost_cents": request.monthly_cost_cents,
        "one_time_cost_cents": request.one_time_cost_cents,
        "start_date": request.start_date,
        "end_date": request.end_date,
    }


@app.get("/ventures/{venture_id}/hire-plans", response_model=list[HirePlanResponse])
def list_hire_plans(
    venture_id: int,
    status: str | None = None,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    rows = list_venture_hire_plans_for_owner(current_user.user_id, venture_id, status=status)
    return [_hire_plan_response(r) for r in rows]


@app.post("/ventures/{venture_id}/hire-plans", response_model=HirePlanResponse)
def create_hire_plan(
    venture_id: int,
    request: CreateHirePlanRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    row = create_venture_hire_plan(
        venture_id=venture_id,
        user_id=current_user.user_id,
        role=request.role,
        employment_type=request.employment_type,
        start_date=request.start_date,
        annual_salary_cents=request.annual_salary_cents,
        burden_percent=request.burden_percent,
        monthly_cost_cents=request.monthly_cost_cents,
        one_time_cost_cents=request.one_time_cost_cents,
        end_date=request.end_date,
    )
    _log_event_safe(
        "hire_plan_created",
        user_id=current_user.user_id,
        venture_id=venture_id,
        metadata={"employment_type": request.employment_type},
    )
    return _hire_plan_response(row)


# Partial update -- edits merge onto the EXISTING row before re-validating
# employee-vs-contractor field shape, since a partial request alone
# cannot know the other side's current values (e.g. changing only
# `role` on an existing employee hire must not require re-sending salary/
# burden). Status transitions (cancel/actualize, §5/§19 of the directive)
# go through this same endpoint -- a dedicated explicit action, never
# inferred, and the row is never deleted either way (§18: "do not
# hard-delete financial planning history").
@app.patch("/ventures/{venture_id}/hire-plans/{hire_plan_id}", response_model=HirePlanResponse)
def update_hire_plan(
    venture_id: int,
    hire_plan_id: int,
    request: UpdateHirePlanRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    existing = get_venture_hire_plan_for_owner(current_user.user_id, venture_id, hire_plan_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Hire plan not found.")

    fields = {k: v for k, v in request.model_dump(exclude_unset=True).items()}

    if fields:
        merged = {**existing, **fields}
        if merged["employment_type"] == "employee":
            if merged.get("annual_salary_cents") is None or merged.get("burden_percent") is None:
                raise HTTPException(status_code=422, detail="An employee hire requires annual_salary_cents and burden_percent.")
        else:
            if merged.get("monthly_cost_cents") is None:
                raise HTTPException(status_code=422, detail="A contractor hire requires monthly_cost_cents.")
        if merged.get("end_date") is not None and merged["end_date"] < merged["start_date"]:
            raise HTTPException(status_code=422, detail="end_date cannot be before start_date.")

    updated = update_venture_hire_plan_for_owner(current_user.user_id, venture_id, hire_plan_id, **fields)
    if updated is None:
        raise HTTPException(status_code=404, detail="Hire plan not found.")

    if "status" in fields:
        _log_event_safe(
            "hire_plan_status_changed",
            user_id=current_user.user_id,
            venture_id=venture_id,
            metadata={"status": fields["status"]},
        )

    return _hire_plan_response(updated)


# Phase 35C §17: a PERSISTED plan vs. a TEMPORARY COMPARISON are
# structurally different -- this endpoint NEVER writes to
# venture_hire_plans. It answers "what would this hire do" (before
# saving) and "hire now vs. later" (called twice with different
# start_date values) using the exact same calculation path a real save
# would use, so the preview a founder sees is never a different
# computation than what they'd get after saving.
@app.post("/ventures/{venture_id}/hire-plans/preview", response_model=HireImpactPreview)
def preview_hire_plan(
    venture_id: int,
    request: CreateHirePlanRequest,
    exclude_hire_plan_id: int | None = None,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    hypothetical = _create_hire_request_to_row(request)
    monthly_cost = compute_hire_monthly_cost_cents(hypothetical)
    annual_cost = compute_hire_annual_cost_cents(hypothetical)

    snapshot = get_latest_venture_financial_snapshot_for_owner(current_user.user_id, venture_id)
    if snapshot is None:
        return HireImpactPreview(
            computed_monthly_cost_cents=monthly_cost,
            computed_annual_cost_cents=annual_cost,
            baseline_projection=[],
            with_hire_projection=[],
        )

    existing_hires = [
        h for h in list_venture_hire_plans_for_owner(current_user.user_id, venture_id)
        if h["id"] != exclude_hire_plan_id
    ]
    existing_items = hire_plan_items_for_projection(existing_hires)

    baseline = project_monthly_cash_flow(snapshot, snapshot["as_of_date"], plan_items=existing_items)

    hypothetical_item = hire_to_plan_item({**hypothetical, "id": -1})
    with_hire_items = existing_items + ([hypothetical_item] if hypothetical_item else [])
    with_hire = project_monthly_cash_flow(snapshot, snapshot["as_of_date"], plan_items=with_hire_items)

    return HireImpactPreview(
        computed_monthly_cost_cents=monthly_cost,
        computed_annual_cost_cents=annual_cost,
        baseline_projection=[ProjectedMonthWithPlan(**m) for m in baseline],
        with_hire_projection=[ProjectedMonthWithPlan(**m) for m in with_hire],
    )


# ---------------------------------------------------------------------------
# Phase 35D -- Operating Scenarios + Financial Plan Reconciliation V1. See
# docs/product/SIE_FINANCIAL_DECISION_ENGINE_V2.md. Same access doctrine
# as 35B/35C: _require_owned_venture() only.
# ---------------------------------------------------------------------------


# Phase 35D §16: this is founder-controlled bookkeeping of MODEL state,
# never a verification/approval gate -- the founder's own "yes/no" answer
# is recorded verbatim, SIE never second-guesses or infers it.
@app.post("/ventures/{venture_id}/financials/reconcile", response_model=VentureFinancialsResponse)
def reconcile_financial_plan(
    venture_id: int,
    request: ReconcilePlanRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    latest = get_latest_venture_financial_snapshot_for_owner(current_user.user_id, venture_id)
    if latest is None:
        raise HTTPException(status_code=404, detail="No financial snapshot exists yet.")

    # Always records that this plan has been asked-and-answered against
    # THIS snapshot (§13: prevents re-nagging on reload, §S) -- "included"
    # additionally actualizes it (§O); "not included" leaves it planned,
    # still contributing to future projections (§P), but not re-asked
    # again unless a NEWER snapshot arrives.
    fields = {"last_reconciled_snapshot_id": latest["id"]}
    if request.included:
        fields["status"] = "actualized"

    if request.plan_kind == "hire":
        existing = get_venture_hire_plan_for_owner(current_user.user_id, venture_id, request.plan_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Hire plan not found.")
        update_venture_hire_plan_for_owner(current_user.user_id, venture_id, request.plan_id, **fields)
    else:
        existing = get_venture_financial_plan_for_owner(current_user.user_id, venture_id, request.plan_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Financial plan not found.")
        update_venture_financial_plan_for_owner(current_user.user_id, venture_id, request.plan_id, **fields)

    _log_event_safe(
        "financial_plan_reconciled",
        user_id=current_user.user_id, venture_id=venture_id,
        metadata={"plan_kind": request.plan_kind, "included": request.included},
    )
    return _build_financials_response(current_user.user_id, venture_id, latest)


# --- Revenue / expense plans --------------------------------------------


@app.get("/ventures/{venture_id}/financial-plans", response_model=list[FinancialPlanResponse])
def list_financial_plans(
    venture_id: int,
    status: str | None = None,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    rows = list_venture_financial_plans_for_owner(current_user.user_id, venture_id, status=status)
    return [_financial_plan_response(r) for r in rows]


def _other_active_financial_plans(
    user_id: str, venture_id: int, plan_type: str, exclude_id: int | None = None, category: str | None = None
) -> list[dict]:
    """Every OTHER currently-`planned` financial plan of the given type
    (and, for expense_change, the same category) -- used by both the
    combined-category-floor check (Case L/K) and the revenue-target
    overlap check (Case M) so a new/edited plan is validated against
    what's ALREADY active, not just itself in isolation."""
    rows = list_venture_financial_plans_for_owner(user_id, venture_id, status="planned")
    return [
        r for r in rows
        if r["id"] != exclude_id
        and r["plan_type"] == plan_type
        and (category is None or r.get("category") == category)
    ]


@app.post("/ventures/{venture_id}/financial-plans", response_model=FinancialPlanResponse)
def create_financial_plan(
    venture_id: int,
    request: CreateFinancialPlanRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    if request.plan_type == "expense_change":
        latest = get_latest_venture_financial_snapshot_for_owner(current_user.user_id, venture_id)
        others = _other_active_financial_plans(current_user.user_id, venture_id, "expense_change", category=request.category)
        other_deltas = sum(o["amount_cents"] for o in others)
        error = validate_expense_plan_amount(latest, request.category, request.amount_cents, other_deltas)
        if error:
            raise HTTPException(status_code=422, detail=error)
    elif request.plan_type == "revenue_target":
        others = _other_active_financial_plans(current_user.user_id, venture_id, "revenue_target")
        error = validate_no_overlapping_revenue_target(others, request.start_date, request.end_date)
        if error:
            raise HTTPException(status_code=422, detail=error)

    row = create_venture_financial_plan(
        venture_id=venture_id, user_id=current_user.user_id, plan_type=request.plan_type,
        label=request.label, amount_cents=request.amount_cents, start_date=request.start_date,
        category=request.category, end_date=request.end_date,
    )
    _log_event_safe(
        "financial_plan_created", user_id=current_user.user_id, venture_id=venture_id,
        metadata={"plan_type": request.plan_type},
    )
    return _financial_plan_response(row)


@app.patch("/ventures/{venture_id}/financial-plans/{plan_id}", response_model=FinancialPlanResponse)
def update_financial_plan(
    venture_id: int,
    plan_id: int,
    request: UpdateFinancialPlanRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    existing = get_venture_financial_plan_for_owner(current_user.user_id, venture_id, plan_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Financial plan not found.")

    fields = request.model_dump(exclude_unset=True)
    if fields:
        merged = {**existing, **fields}
        if merged["plan_type"] == "expense_change" and ("amount_cents" in fields or "category" in fields):
            latest = get_latest_venture_financial_snapshot_for_owner(current_user.user_id, venture_id)
            others = _other_active_financial_plans(
                current_user.user_id, venture_id, "expense_change", exclude_id=plan_id, category=merged["category"]
            )
            other_deltas = sum(o["amount_cents"] for o in others)
            error = validate_expense_plan_amount(latest, merged["category"], merged["amount_cents"], other_deltas)
            if error:
                raise HTTPException(status_code=422, detail=error)
        if merged["plan_type"] == "revenue_target" and ("start_date" in fields or "end_date" in fields):
            others = _other_active_financial_plans(current_user.user_id, venture_id, "revenue_target", exclude_id=plan_id)
            error = validate_no_overlapping_revenue_target(others, merged["start_date"], merged.get("end_date"))
            if error:
                raise HTTPException(status_code=422, detail=error)
        if merged.get("end_date") is not None and merged["end_date"] < merged["start_date"]:
            raise HTTPException(status_code=422, detail="end_date cannot be before start_date.")

    updated = update_venture_financial_plan_for_owner(current_user.user_id, venture_id, plan_id, **fields)
    if updated is None:
        raise HTTPException(status_code=404, detail="Financial plan not found.")

    if "status" in fields:
        _log_event_safe(
            "financial_plan_status_changed", user_id=current_user.user_id, venture_id=venture_id,
            metadata={"status": fields["status"]},
        )
    return _financial_plan_response(updated)


def _project_with_plan_response(months: list[dict]) -> list[ScenarioProjectedMonth]:
    return [ScenarioProjectedMonth(**m) for m in months]


# Ephemeral -- never writes to venture_financial_plans, identical
# discipline to POST /ventures/{id}/hire-plans/preview (§17 of the
# directive: PERSISTED PLAN vs. TEMPORARY COMPARISON).
@app.post("/ventures/{venture_id}/financial-plans/preview", response_model=FinancialPlanImpactPreview)
def preview_financial_plan(
    venture_id: int,
    request: CreateFinancialPlanRequest,
    exclude_plan_id: int | None = None,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    snapshot = get_latest_venture_financial_snapshot_for_owner(current_user.user_id, venture_id)
    if snapshot is None:
        return FinancialPlanImpactPreview(baseline_projection=[], with_plan_projection=[])

    all_hires = list_venture_hire_plans_for_owner(current_user.user_id, venture_id)
    existing_financial_plans = [
        p for p in list_venture_financial_plans_for_owner(current_user.user_id, venture_id)
        if p["id"] != exclude_plan_id
    ]
    existing_items = _all_plan_items_for_projection(all_hires, existing_financial_plans)
    baseline = project_monthly_cash_flow(snapshot, snapshot["as_of_date"], plan_items=existing_items)

    hypothetical_row = {
        "id": -1, "plan_type": request.plan_type, "category": request.category,
        "amount_cents": request.amount_cents, "start_date": request.start_date, "end_date": request.end_date,
    }
    hypothetical_item = (
        expense_plan_to_plan_item(hypothetical_row) if request.plan_type == "expense_change"
        else revenue_plan_to_plan_item(hypothetical_row)
    )
    with_plan = project_monthly_cash_flow(snapshot, snapshot["as_of_date"], plan_items=existing_items + [hypothetical_item])

    return FinancialPlanImpactPreview(
        baseline_projection=_project_with_plan_response(baseline),
        with_plan_projection=_project_with_plan_response(with_plan),
    )


# --- Scenarios -------------------------------------------------------------


# Phase 35D-A §13/§16: founder-facing text must read "March 2027," never
# the raw ISO date a DB row or request model carries -- mirrors
# dashboard/lib/finance/money.ts::formatMonthYear() exactly so a
# scenario's assumption bullets (built server-side) read identically to
# every other date the founder sees on the same page (built client-side).
_MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _format_month_year(value) -> str:
    d = date.fromisoformat(value) if isinstance(value, str) else value
    return f"{_MONTH_NAMES[d.month - 1]} {d.year}"


# Mirrors dashboard/components/finance/FinanceOverview.tsx's own
# EXPENSE_CATEGORY_LABELS exactly -- a raw category code like
# "professional_services" must never reach founder-facing text.
_EXPENSE_CATEGORY_DISPLAY_LABELS = {
    "payroll": "Payroll",
    "contractors": "Contractors",
    "software": "Software",
    "marketing": "Marketing",
    "rent": "Rent",
    "professional_services": "Professional services",
    "other": "Other",
}


def _plan_label(kind: str, row: dict) -> str:
    """
    Phase 35D-B §6 (Case F): describes the actual financial CHANGE, never
    the plan's own arbitrary founder-given nickname. 35D's original
    version prefixed every line with `{row['label']}: ...` -- inside a
    scenario/comparison, that nickname carries no necessary information
    the description itself doesn't already convey, and can actively
    contradict the scenario's own name (a plan named "Growth" showing up,
    unremarked, inside a scenario named "Conservative Plan"). The
    founder's own label is still the PRIMARY, bolded line everywhere a
    plan is shown on its own (Planned Changes) -- only the assumption
    list built for a plan COMBINATION drops it in favor of a plain
    description of what actually changes.
    """
    if kind == "hire":
        cost = compute_hire_monthly_cost_cents(row)
        cost_label = f"{cost / 100:,.0f}/mo" if cost is not None else "cost unknown"
        return f"{row['role']} starts {_format_month_year(row['start_date'])} (${cost_label})"
    if row["plan_type"] == "revenue_target":
        return f"Revenue becomes ${row['amount_cents'] / 100:,.0f}/month starting {_format_month_year(row['start_date'])}"
    category_label = _EXPENSE_CATEGORY_DISPLAY_LABELS.get(row["category"], row["category"])
    direction = "increases" if row["amount_cents"] >= 0 else "decreases"
    return f"{category_label} spending {direction} ${abs(row['amount_cents']) / 100:,.0f}/month starting {_format_month_year(row['start_date'])}"


def _build_scenario_response(user_id: str, venture_id: int, scenario: dict) -> ScenarioResponse:
    """Computed live, every call -- see ScenarioResponse's own docstring
    for why nothing here is stored. A cancelled/actualized plan id still
    referenced by the scenario is silently skipped (never an error).

    Phase 40A-FIX: this used to issue one DB round trip per id in
    hire_plan_ids/financial_plan_ids (a genuine N+1 -- Phase 40A's own
    audit finding). Now issues exactly TWO queries total regardless of
    how many plans the scenario references
    (list_venture_hire_plans_for_owner_by_ids/
    list_venture_financial_plans_for_owner_by_ids, each a single
    `WHERE id = ANY(...)` with ownership enforced in the query itself),
    then reconstructs each list in the scenario's OWN stored id order via
    an in-memory dict lookup -- the exact same filter (status='planned'
    only) and the exact same output order as the original per-id loop,
    just batched."""
    snapshot = get_latest_venture_financial_snapshot_for_owner(user_id, venture_id)

    hire_by_id = {
        h["id"]: h
        for h in list_venture_hire_plans_for_owner_by_ids(user_id, venture_id, scenario["hire_plan_ids"], status="planned")
    }
    financial_by_id = {
        p["id"]: p
        for p in list_venture_financial_plans_for_owner_by_ids(user_id, venture_id, scenario["financial_plan_ids"], status="planned")
    }
    hires = [hire_by_id[hid] for hid in scenario["hire_plan_ids"] if hid in hire_by_id]
    financial_plans = [financial_by_id[pid] for pid in scenario["financial_plan_ids"] if pid in financial_by_id]
    assumptions = [_plan_label("hire", h) for h in hires] + [_plan_label("financial", p) for p in financial_plans]

    projection: list[dict] = []
    if snapshot is not None:
        items = _all_plan_items_for_projection(hires, financial_plans)
        projection = project_monthly_cash_flow(snapshot, snapshot["as_of_date"], plan_items=items)

    depletion = next((m for m in projection if m["depleted"]), None)
    return ScenarioResponse(
        **scenario,
        assumptions=assumptions,
        projection=_project_with_plan_response(projection),
        ending_cash_at_horizon_cents=projection[-1]["ending_cash_cents"] if projection else None,
        depletion_date=depletion["date"] if depletion else None,
    )


@app.get("/ventures/{venture_id}/scenarios", response_model=list[ScenarioResponse])
def list_scenarios(
    venture_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    rows = list_venture_financial_scenarios_for_owner(current_user.user_id, venture_id)
    return [_build_scenario_response(current_user.user_id, venture_id, r) for r in rows]


@app.post("/ventures/{venture_id}/scenarios", response_model=ScenarioResponse)
def create_scenario(
    venture_id: int,
    request: CreateScenarioRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    # Ownership of every referenced plan id, re-scoped through THIS
    # venture -- never trusted as a bare id (§K of the directive: "a
    # scenario cannot reference another user's plan"). Phase 40A-FIX:
    # batched into one query per id-list (any status is a valid
    # reference here, matching the original per-id lookup's own
    # unfiltered behavior) instead of one query per id.
    owned_hire_ids = {
        h["id"] for h in list_venture_hire_plans_for_owner_by_ids(current_user.user_id, venture_id, request.hire_plan_ids)
    }
    for hid in request.hire_plan_ids:
        if hid not in owned_hire_ids:
            raise HTTPException(status_code=404, detail=f"Hire plan {hid} not found for this venture.")
    owned_financial_ids = {
        p["id"] for p in list_venture_financial_plans_for_owner_by_ids(current_user.user_id, venture_id, request.financial_plan_ids)
    }
    for pid in request.financial_plan_ids:
        if pid not in owned_financial_ids:
            raise HTTPException(status_code=404, detail=f"Financial plan {pid} not found for this venture.")

    row = create_venture_financial_scenario(
        venture_id=venture_id, user_id=current_user.user_id, name=request.name,
        hire_plan_ids=request.hire_plan_ids, financial_plan_ids=request.financial_plan_ids,
    )
    _log_event_safe("financial_scenario_created", user_id=current_user.user_id, venture_id=venture_id, metadata={})
    return _build_scenario_response(current_user.user_id, venture_id, row)


@app.patch("/ventures/{venture_id}/scenarios/{scenario_id}", response_model=ScenarioResponse)
def update_scenario(
    venture_id: int,
    scenario_id: int,
    request: UpdateScenarioRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    existing = get_venture_financial_scenario_for_owner(current_user.user_id, venture_id, scenario_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Scenario not found.")

    fields = request.model_dump(exclude_unset=True)
    # Phase 40A-FIX: batched, same reasoning as create_scenario() above.
    if "hire_plan_ids" in fields:
        owned_hire_ids = {
            h["id"] for h in list_venture_hire_plans_for_owner_by_ids(current_user.user_id, venture_id, fields["hire_plan_ids"])
        }
        for hid in fields["hire_plan_ids"]:
            if hid not in owned_hire_ids:
                raise HTTPException(status_code=404, detail=f"Hire plan {hid} not found for this venture.")
    if "financial_plan_ids" in fields:
        owned_financial_ids = {
            p["id"] for p in list_venture_financial_plans_for_owner_by_ids(current_user.user_id, venture_id, fields["financial_plan_ids"])
        }
        for pid in fields["financial_plan_ids"]:
            if pid not in owned_financial_ids:
                raise HTTPException(status_code=404, detail=f"Financial plan {pid} not found for this venture.")

    updated = update_venture_financial_scenario_for_owner(current_user.user_id, venture_id, scenario_id, **fields)
    if updated is None:
        raise HTTPException(status_code=404, detail="Scenario not found.")
    return _build_scenario_response(current_user.user_id, venture_id, updated)


@app.delete("/ventures/{venture_id}/scenarios/{scenario_id}")
def delete_scenario(
    venture_id: int,
    scenario_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    deleted = delete_venture_financial_scenario_for_owner(current_user.user_id, venture_id, scenario_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Scenario not found.")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Phase 38D-A -- Financial Commitment Persistence + Frozen Expectation V1.
# See docs/product/SIE_COMMITTED_PLAN_LEARNING_ARCHITECTURE_V1.md for the
# accepted architecture.
#
# A Committed Plan is NOT a scenario -- venture_financial_scenarios above
# stays exactly what it already is: hypothetical, always live-recomputed.
# This section only ever READS venture_hire_plans/venture_financial_plans/
# venture_financial_scenarios/venture_financial_snapshots/venture_decisions
# -- it never writes to any of them. The one new write path
# (create_venture_financial_commitment) is append-only by construction:
# there is no PATCH/DELETE endpoint in this phase (§3/§25 of the
# directive).


def _plan_snapshot_item(source_kind: str, row: dict) -> dict:
    """One included plan/hire's own input VALUES, frozen at commitment
    time -- never a bare id, since the underlying row is confirmed
    mutable (Phase 35C/35D's own update-in-place design). See
    PlanSnapshotItem's own docstring
    (app/models/venture_financial_commitments.py)."""
    if source_kind == "hire":
        return {
            "id": row["id"], "kind": "hire", "label": row["role"],
            "start_date": row["start_date"], "end_date": row.get("end_date"),
            "role": row["role"], "employment_type": row["employment_type"],
            "annual_salary_cents": row.get("annual_salary_cents"),
            "burden_percent": row.get("burden_percent"),
            "monthly_cost_cents": compute_hire_monthly_cost_cents(row),
            "one_time_cost_cents": row.get("one_time_cost_cents"),
        }
    return {
        "id": row["id"], "kind": row["plan_type"], "label": row["label"],
        "start_date": row["start_date"], "end_date": row.get("end_date"),
        "category": row.get("category"), "amount_cents": row["amount_cents"],
    }


@app.post("/ventures/{venture_id}/financial-commitments", response_model=FinancialCommitmentResponse)
def create_financial_commitment(
    venture_id: int,
    request: CreateFinancialCommitmentRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    user_id = current_user.user_id

    # §4/§18 of the 38D-A directive: exactly one commitment source -- a
    # saved scenario (resolved server-side into ITS OWN current
    # hire_plan_ids/financial_plan_ids, never trusting a client-supplied
    # copy) or an explicit set of individual plan ids.
    # CreateFinancialCommitmentRequest's own validator already rejects
    # supplying both/neither.
    scenario_name = None
    if request.scenario_id is not None:
        scenario = get_venture_financial_scenario_for_owner(user_id, venture_id, request.scenario_id)
        if scenario is None:
            raise HTTPException(status_code=404, detail="Scenario not found for this venture.")
        scenario_name = scenario["name"]
        hire_plan_ids = scenario["hire_plan_ids"]
        financial_plan_ids = scenario["financial_plan_ids"]
    else:
        hire_plan_ids = request.hire_plan_ids
        financial_plan_ids = request.financial_plan_ids

    # Ownership of every referenced plan id, re-scoped through THIS
    # venture -- identical discipline to create_scenario()'s own
    # validation (§11: fail closed on a foreign plan/scenario/decision).
    # Phase 40A-FIX: batched into one query per id-list (any status is a
    # valid reference here -- status filtering happens separately below,
    # matching the original per-id lookup's own unfiltered behavior)
    # instead of one query per id, while preserving the exact
    # hire_plan_ids/financial_plan_ids order for plan_snapshot.
    owned_hires_by_id = {h["id"]: h for h in list_venture_hire_plans_for_owner_by_ids(user_id, venture_id, hire_plan_ids)}
    hires = []
    for hid in hire_plan_ids:
        if hid not in owned_hires_by_id:
            raise HTTPException(status_code=404, detail=f"Hire plan {hid} not found for this venture.")
        hires.append(owned_hires_by_id[hid])
    owned_financial_by_id = {
        p["id"]: p for p in list_venture_financial_plans_for_owner_by_ids(user_id, venture_id, financial_plan_ids)
    }
    financial_plans = []
    for pid in financial_plan_ids:
        if pid not in owned_financial_by_id:
            raise HTTPException(status_code=404, detail=f"Financial plan {pid} not found for this venture.")
        financial_plans.append(owned_financial_by_id[pid])

    if request.related_decision_id is not None:
        decisions = list_venture_decisions_for_owner(user_id, venture_id)
        if not any(d["id"] == request.related_decision_id for d in decisions):
            raise HTTPException(status_code=404, detail="Decision not found for this venture.")

    # §8: never permit a commitment without a real source snapshot --
    # identical guard to POST .../financials/reconcile's own.
    snapshot = get_latest_venture_financial_snapshot_for_owner(user_id, venture_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No financial snapshot exists yet.")

    # §21: the frozen plan_snapshot/expected_monthly must agree on
    # exactly what was included -- reuse the SAME status='planned' filter
    # the live scenario engine already applies (hire_plan_items_for_projection/
    # financial_plan_items_for_projection's own internal filter, identical
    # to _build_scenario_response's own explicit one above) so a
    # cancelled/actualized plan is silently excluded here exactly as it
    # already is everywhere else -- never silently included (Case T/U).
    active_hires = [h for h in hires if h["status"] == "planned"]
    active_financial_plans = [p for p in financial_plans if p["status"] == "planned"]

    plan_items = _all_plan_items_for_projection(active_hires, active_financial_plans)
    expected_monthly = project_monthly_cash_flow(snapshot, snapshot["as_of_date"], plan_items=plan_items)

    # §20: NULL != 0. project_monthly_cash_flow() returns [] ONLY when
    # cash/revenue/expenses are unknown (its own docstring) -- never a
    # partial or fake projection. An honest validation error, no row
    # written (§10 transactional consistency: calculation happens BEFORE
    # any insert is attempted).
    if not expected_monthly:
        raise HTTPException(
            status_code=422,
            detail="Cannot commit: your latest financial snapshot doesn't have complete cash, revenue, "
                   "and expense data yet.",
        )

    plan_snapshot = (
        [_plan_snapshot_item("hire", h) for h in active_hires]
        + [_plan_snapshot_item("financial", p) for p in active_financial_plans]
    )

    commitment = create_venture_financial_commitment(
        venture_id=venture_id,
        user_id=user_id,
        source_snapshot_id=snapshot["id"],
        plan_snapshot=[PlanSnapshotItem(**item).model_dump(mode="json") for item in plan_snapshot],
        calculation_version=FINANCIAL_PROJECTION_CALCULATION_VERSION,
        projection_start=snapshot["as_of_date"],
        projection_horizon_months=DEFAULT_PROJECTION_HORIZON_MONTHS,
        expected_monthly=[m.model_dump(mode="json") for m in _project_with_plan_response(expected_monthly)],
        hire_plan_ids=[h["id"] for h in active_hires],
        financial_plan_ids=[p["id"] for p in active_financial_plans],
        scenario_id=request.scenario_id,
        scenario_name=scenario_name,
        related_decision_id=request.related_decision_id,
        founder_rationale=request.founder_rationale,
        idempotency_key=request.idempotency_key,
    )

    _log_event_safe(
        "financial_commitment_created",
        user_id=user_id, venture_id=venture_id,
        metadata={"scenario_id": request.scenario_id, "plan_count": len(plan_snapshot)},
    )

    return FinancialCommitmentResponse(**commitment)


@app.get("/ventures/{venture_id}/financial-commitments", response_model=list[FinancialCommitmentResponse])
def list_financial_commitments(
    venture_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    rows = list_venture_financial_commitments_for_owner(current_user.user_id, venture_id)
    return [FinancialCommitmentResponse(**row) for row in rows]


# Phase 39B -- Contextual Hiring History Retrieval V1. A pure read: no
# write, no new table, no mutation of anything. Reuses the SAME two
# ownership-scoped reads (list_venture_financial_commitments_for_owner,
# list_venture_financial_snapshots_for_owner) and the SAME comparison
# function (build_commitment_comparison) every other commitment endpoint
# already uses -- see app/ai/hiring_history.py's own module docstring
# for the full eligibility/selection contract. `None` (a null body) is
# the honest, expected "no relevant history" result -- the SAME
# convention `GET /me/startup-claims/{startup_id}` already uses, never
# an error.
#
# MUST be declared before the GET .../{commitment_id} route immediately
# below -- FastAPI/Starlette matches path routes in declaration order,
# and a static segment ("relevant-hire-history") registered AFTER a
# same-depth `{commitment_id}: int` route would otherwise be swallowed
# by it and rejected with a 422 int-parsing error instead of ever
# reaching this handler.
@app.get(
    "/ventures/{venture_id}/financial-commitments/relevant-hire-history",
    response_model=RelevantHireHistoryResponse | None,
)
def get_relevant_hire_history(
    venture_id: int,
    exclude_commitment_id: int | None = None,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    commitments = list_venture_financial_commitments_for_owner(current_user.user_id, venture_id)
    snapshots = list_venture_financial_snapshots_for_owner(current_user.user_id, venture_id)

    def _comparison_for(commitment: dict) -> dict:
        return build_commitment_comparison(commitment, snapshots, compute_derived_metrics)

    result = find_relevant_hire_history(commitments, _comparison_for, exclude_commitment_id)
    if result is None:
        return None
    return RelevantHireHistoryResponse(**result)


# GET-by-id returns the row EXACTLY as stored -- see
# get_venture_financial_commitment_for_owner()'s own docstring
# (app/database/db.py). No recomputation happens on this path, ever.
@app.get("/ventures/{venture_id}/financial-commitments/{commitment_id}", response_model=FinancialCommitmentResponse)
def get_financial_commitment(
    venture_id: int,
    commitment_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    commitment = get_venture_financial_commitment_for_owner(current_user.user_id, venture_id, commitment_id)
    if commitment is None:
        raise HTTPException(status_code=404, detail="Commitment not found.")
    return FinancialCommitmentResponse(**commitment)


# Phase 38D-B -- Committed Expectation vs Actual V1. Pure read: no new
# table, no write, no mutation of the commitment row. Reuses the SAME two
# ownership-scoped reads (get_venture_financial_commitment_for_owner,
# list_venture_financial_snapshots_for_owner) every other Finance
# endpoint already uses -- see app/ai/commitment_comparison.py's own
# module docstring for the full comparison contract.
@app.get(
    "/ventures/{venture_id}/financial-commitments/{commitment_id}/comparison",
    response_model=FinancialCommitmentComparisonResponse,
)
def get_financial_commitment_comparison(
    venture_id: int,
    commitment_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    commitment = get_venture_financial_commitment_for_owner(current_user.user_id, venture_id, commitment_id)
    if commitment is None:
        raise HTTPException(status_code=404, detail="Commitment not found.")
    snapshots = list_venture_financial_snapshots_for_owner(current_user.user_id, venture_id)
    comparison = build_commitment_comparison(commitment, snapshots, compute_derived_metrics)
    return FinancialCommitmentComparisonResponse(**comparison)


# Phase 38D-C -- Founder Explanation + Learning Capture V1. The ONLY
# write path for founder_explanation/explanation_recorded_at -- see
# update_venture_financial_commitment_explanation_for_owner()'s own
# docstring (app/database/db.py) for exactly which two columns this
# touches and, just as importantly, which columns it structurally
# cannot touch. §3 of the directive: explanation capture requires at
# least one actual observation to already exist -- re-derives
# `comparison_status` via the SAME pure function the comparison endpoint
# itself uses (no new eligibility concept, no invented variance
# threshold) and rejects (409) while still `awaiting_actuals`.
@app.patch(
    "/ventures/{venture_id}/financial-commitments/{commitment_id}/explanation",
    response_model=FinancialCommitmentResponse,
)
def update_financial_commitment_explanation(
    venture_id: int,
    commitment_id: int,
    request: UpdateFinancialCommitmentExplanationRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    commitment = get_venture_financial_commitment_for_owner(current_user.user_id, venture_id, commitment_id)
    if commitment is None:
        raise HTTPException(status_code=404, detail="Commitment not found.")

    snapshots = list_venture_financial_snapshots_for_owner(current_user.user_id, venture_id)
    comparison = build_commitment_comparison(commitment, snapshots, compute_derived_metrics)
    if comparison["comparison_status"] == "awaiting_actuals":
        raise HTTPException(
            status_code=409,
            detail="An explanation can only be recorded once at least one actual financial snapshot has been observed for this plan.",
        )

    updated = update_venture_financial_commitment_explanation_for_owner(
        current_user.user_id, venture_id, commitment_id, request.founder_explanation
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Commitment not found.")

    _log_event_safe(
        "financial_commitment_explanation_recorded",
        user_id=current_user.user_id, venture_id=venture_id, metadata={},
    )
    return FinancialCommitmentResponse(**updated)


@app.get("/ventures/{venture_id}/decisions", response_model=list[VentureDecisionResponse])
def list_venture_decisions(
    venture_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)
    decisions = list_venture_decisions_for_owner(current_user.user_id, venture_id)
    return [VentureDecisionResponse(**row) for row in decisions]


# Phase 34D §10: SIE's recommendation and the founder's actual choice are
# both required fields on the SAME request, but are never collapsed --
# they are stored in two separate columns and rendered as two separate
# facts everywhere downstream (§13 founder authority: the founder is
# never required to agree with SIE).
@app.post("/ventures/{venture_id}/decisions", response_model=VentureDecisionResponse)
def create_decision(
    venture_id: int,
    request: CreateDecisionRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)

    if request.related_mission_id is not None:
        missions = list_venture_missions_for_owner(current_user.user_id, venture_id)
        if not any(m["id"] == request.related_mission_id for m in missions):
            raise HTTPException(status_code=404, detail="Mission not found for this venture.")
    if request.supersedes_decision_id is not None:
        decisions = list_venture_decisions_for_owner(current_user.user_id, venture_id)
        if not any(d["id"] == request.supersedes_decision_id for d in decisions):
            raise HTTPException(status_code=404, detail="Decision not found for this venture.")
    # §17: every id in evidence_ids must belong to this venture -- never
    # trusted as bare client-supplied ids.
    if request.evidence_ids:
        venture_evidence_ids = {e["id"] for e in list_venture_evidence_for_owner(current_user.user_id, venture_id)}
        if not set(request.evidence_ids).issubset(venture_evidence_ids):
            raise HTTPException(status_code=404, detail="One or more evidence ids do not belong to this venture.")

    decision = create_venture_decision(
        venture_id=venture_id,
        user_id=current_user.user_id,
        sie_recommendation=request.sie_recommendation,
        sie_reasoning=request.sie_reasoning,
        founder_choice=request.founder_choice,
        related_mission_id=request.related_mission_id,
        founder_rationale=request.founder_rationale,
        evidence_ids=request.evidence_ids,
        supersedes_decision_id=request.supersedes_decision_id,
        idempotency_key=request.idempotency_key,
    )

    # A decision resolves the question its mission was testing -- mark
    # that mission completed, the same transition the founder's own
    # "complete" action already produces elsewhere (§7: "do not create a
    # second Tests table" extends to "do not create a second completion
    # mechanism" -- this reuses update_venture_mission_status_for_owner()
    # unchanged).
    if request.related_mission_id is not None:
        update_venture_mission_status_for_owner(
            user_id=current_user.user_id,
            venture_id=venture_id,
            mission_id=request.related_mission_id,
            new_status="completed",
        )

    _log_event_safe(
        "decision_recorded",
        user_id=current_user.user_id,
        venture_id=venture_id,
        metadata={"founder_choice": decision["founder_choice"]},
    )

    return VentureDecisionResponse(**decision)


# ---------------------------------------------------------------------------
# Phase 23 -- Universal Founder Capture V1. "Save what happened" -- one
# atomic write (db.capture_venture_observation()) composing the SAME
# create/learning/complete venture_missions fields the three endpoints
# above already write individually. Not a new architecture: the response
# is the same VentureMissionResponse, the resulting row is indistinguishable
# from one an ordinary mission flow could have produced, and it shows up
# in GET /ventures/{id}/history through the exact same, unmodified
# source-to-event mapping. THE VPS FIREWALL is unchanged: this endpoint
# never calls compute_vps()/update_modeled_venture_for_user() -- see
# db.capture_venture_observation()'s own docstring.
#
# Title derivation: the founder is only ever asked "What happened?" --
# never a separate title field (Part 2's own instruction). The stored
# title is the first line of their own text, trimmed to fit the existing
# title column's 300-char limit (shared with every other mission title),
# falling back to a generic label only for the pathological case of a
# single very long line with no natural break.
# ---------------------------------------------------------------------------


def _derive_capture_title(text_value: str) -> str:
    first_line = text_value.strip().splitlines()[0].strip()
    if not first_line:
        return "What happened"
    if len(first_line) <= 300:
        return first_line
    return first_line[:297].rstrip() + "..."


@app.post("/ventures/{venture_id}/capture", response_model=VentureMissionResponse)
def capture_observation(
    venture_id: int,
    request: CaptureObservationRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)

    mission = capture_venture_observation(
        venture_id=venture_id,
        user_id=current_user.user_id,
        title=_derive_capture_title(request.text),
        learning_summary=request.text.strip(),
        related_category=request.category,
    )
    # Phase 28, Part 2/6: `category` is the founder's own pre-existing
    # optional chip selection (customer_conversation / product / etc.) --
    # already a closed, safe enum on CaptureObservationRequest, never the
    # captured text itself. Signal-count/outcome-class classification
    # (captureSignals.ts) is frontend-only and runs AFTER this call
    # succeeds -- deliberately not duplicated server-side just to enrich
    # this event's metadata (see docs/product/PRODUCT_ANALYTICS_V1.md's
    # own "events rejected/deferred" section for the full reasoning).
    _log_event_safe(
        "capture_recorded",
        user_id=current_user.user_id,
        venture_id=venture_id,
        metadata={"category": request.category},
    )
    return VentureMissionResponse(**mission)


# ---------------------------------------------------------------------------
# Phase 16 -- Founder Progress / Venture History V1.
#
# get_venture_history() is a READ-ONLY assembly over data that ALREADY
# exists once this phase's own single new write path (update_venture()'s
# create_venture_model_update() call, above) has run -- no new "event"
# table beyond venture_model_updates itself, no generic event platform.
# Exactly THREE queries (the venture row, its missions, its model
# updates), all already-existing single-query functions except the one
# new one -- never N+1 (Part 17).
#
# Source -> event mapping (Part 16's own required documentation):
#   venture_created    <- modeled_ventures.created_at (exact, real)
#   action_added       <- venture_missions.created_at (exact, real; this
#                         IS "when the action was added" -- there is no
#                         separate persisted "started" moment distinct
#                         from creation, so this event is honestly framed
#                         as "added," not a fabricated "started at time X
#                         the founder didn't actually start it at")
#   learning_recorded  <- venture_missions.learning_recorded_at +
#                         .learning_summary (verbatim, exact, real)
#   action_completed   <- venture_missions.completed_at (exact, real)
#   model_updated       <- venture_model_updates (exact, real -- the one
#                         genuinely new persistence this phase added)
# ---------------------------------------------------------------------------

_CATEGORY_CHANGE_EPSILON = 0.05  # mirrors dashboard's own categoryChangeExplain.ts threshold


def _parse_jsonb(value):
    if isinstance(value, str):
        return json.loads(value)
    return value


def _diff_category_changes(before_categories: list, after_categories: list) -> list[VentureHistoryCategoryChange]:
    before_by_key = {c["key"]: c.get("score") for c in before_categories}
    changes = []
    for cat in after_categories:
        key = cat["key"]
        before_score = before_by_key.get(key)
        after_score = cat.get("score")
        if before_score is None and after_score is None:
            continue
        if before_score is not None and after_score is not None and abs(after_score - before_score) < _CATEGORY_CHANGE_EPSILON:
            continue
        changes.append(VentureHistoryCategoryChange(
            key=key, label=cat.get("label", key), before=before_score, after=after_score,
        ))
    return changes


# Phase 24 -- Weekly Founder Review V1, Part 7. A small, CURATED set of
# assumption fields worth showing as a human-readable "before -> after"
# line ("Price point $500 -> $299") -- deliberately not every field in
# VentureAssumptions (most, like free-text market_description, have no
# honest single-line diff). Each entry is (dotted path, display label,
# formatter). Mirrors CaptureWhatHappened.tsx's own fieldPathLabel()/
# formatValue() set on the frontend (Phase 23) for the three fields it
# already knows how to propose, extended with a few more numeric fields
# that already exist on VentureAssumptions and are equally safe to diff.
def _fmt_dollars(value) -> str:
    return f"${value:,.0f}"


def _fmt_count(value) -> str:
    return f"{value:,.0f}" if isinstance(value, (int, float)) else str(value)


def _fmt_percent(value) -> str:
    return f"{value:g}%"


_ASSUMPTION_DIFF_FIELDS: list[tuple[str, str, str, callable]] = [
    # (category, key, label, formatter)
    ("economics", "price_point", "Price point", _fmt_dollars),
    ("economics", "expected_gross_margin_pct", "Gross margin", _fmt_percent),
    ("validation", "customer_interviews", "Customer interviews", _fmt_count),
    ("validation", "waitlist_signups", "Waitlist signups", _fmt_count),
    ("validation", "paying_customers", "Paying customers", _fmt_count),
    ("validation", "monthly_revenue", "Monthly revenue", _fmt_dollars),
    ("validation", "retention_pct", "Retention", _fmt_percent),
]


def _diff_assumption_changes(before_assumptions: dict, after_assumptions: dict) -> list[VentureHistoryAssumptionChange]:
    changes: list[VentureHistoryAssumptionChange] = []
    for category, key, label, formatter in _ASSUMPTION_DIFF_FIELDS:
        before_value = (before_assumptions.get(category) or {}).get(key)
        after_value = (after_assumptions.get(category) or {}).get(key)
        if before_value == after_value:
            continue
        if before_value is None and after_value is None:
            continue
        changes.append(VentureHistoryAssumptionChange(
            field_path=f"{category}.{key}",
            label=label,
            before="Unknown" if before_value is None else formatter(before_value),
            after="Unknown" if after_value is None else formatter(after_value),
        ))
    return changes


@app.get("/ventures/{venture_id}/history", response_model=VentureHistoryResponse)
def get_venture_history(
    venture_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    venture = _require_owned_venture(current_user, venture_id)
    missions = list_venture_missions_for_owner(current_user.user_id, venture_id)
    model_updates = list_venture_model_updates_for_owner(current_user.user_id, venture_id)
    # Phase 34E -- History becomes Learning History: two more read-only
    # sources over data Phase 34D already persists (venture_decisions,
    # venture_evidence) -- no new table, no new query pattern beyond what
    # CurrentQuestionCard's own GET endpoints already do.
    decisions = list_venture_decisions_for_owner(current_user.user_id, venture_id)
    evidence = list_venture_evidence_for_owner(current_user.user_id, venture_id)

    missions_by_id = {m["id"]: m for m in missions}
    events: list[VentureHistoryEvent] = []

    for mission in missions:
        events.append(VentureHistoryEvent(
            event_type="action_added",
            occurred_at=mission["created_at"],
            title=mission["title"],
            mission_id=mission["id"],
            mission_title=mission["title"],
        ))
        if mission.get("learning_recorded_at") is not None and mission.get("learning_summary"):
            events.append(VentureHistoryEvent(
                event_type="learning_recorded",
                occurred_at=mission["learning_recorded_at"],
                title="Learning recorded",
                description=mission["learning_summary"],
                mission_id=mission["id"],
                mission_title=mission["title"],
            ))
        if mission.get("completed_at") is not None:
            events.append(VentureHistoryEvent(
                event_type="action_completed",
                occurred_at=mission["completed_at"],
                title=mission["title"],
                mission_id=mission["id"],
                mission_title=mission["title"],
            ))

    all_category_changes: list[VentureHistoryCategoryChange] = []
    for update in model_updates:
        before_categories = _parse_jsonb(update["before_categories"]) or []
        after_categories = _parse_jsonb(update["after_categories"]) or []
        category_changes = _diff_category_changes(before_categories, after_categories)
        all_category_changes.extend(category_changes)

        before_assumptions = _parse_jsonb(update.get("before_assumptions")) or {}
        after_assumptions = _parse_jsonb(update.get("after_assumptions")) or {}
        assumption_changes = _diff_assumption_changes(before_assumptions, after_assumptions)

        related_mission = missions_by_id.get(update["related_mission_id"]) if update.get("related_mission_id") else None
        events.append(VentureHistoryEvent(
            event_type="model_updated",
            occurred_at=update["created_at"],
            title="Model updated",
            description=(related_mission["learning_summary"] if related_mission and related_mission.get("learning_summary") else None),
            before_vps=update["before_vps"],
            after_vps=update["after_vps"],
            category_changes=category_changes,
            assumption_changes=assumption_changes,
            mission_id=related_mission["id"] if related_mission else None,
            mission_title=related_mission["title"] if related_mission else None,
        ))

    # Phase 34E: a decision, once made, is always shown -- a reversed
    # decision (supersedes_decision_id set on a LATER row) means the
    # earlier one is superseded; only show each decision once, and prefer
    # showing it as itself (supersession is about which decision is
    # CURRENT, not about hiding that an earlier one was ever made) --
    # so, unlike evidence/outcome below, every decision row gets an event,
    # since a reversed decision is still real history a founder made.
    for decision in decisions:
        events.append(VentureHistoryEvent(
            event_type="decision_recorded",
            occurred_at=decision["decided_at"],
            title="Decision recorded",
            sie_recommendation=decision["sie_recommendation"],
            founder_choice=decision["founder_choice"],
            founder_rationale=decision.get("founder_rationale"),
            mission_id=decision.get("related_mission_id"),
            mission_title=(
                missions_by_id.get(decision["related_mission_id"], {}).get("title")
                if decision.get("related_mission_id") else None
            ),
        ))

    # Outcomes are a stream of check-ins on a past decision (§18
    # append-only) -- a corrected/superseded one is never shown a second
    # time once superseded, matching CurrentQuestionCard's own
    # `!e.superseded_by_id` filtering for "the current view."
    for row in evidence:
        if row["evidence_type"] != "longitudinal_outcome" or row.get("superseded_by_id"):
            continue
        events.append(VentureHistoryEvent(
            event_type="outcome_recorded",
            occurred_at=row["recorded_at"],
            title="What happened afterward",
            description=row["statement"],
            relationship=row.get("relationship"),
        ))

    # The venture's own creation -- always the earliest event. "Initial
    # VPS" is the earliest known VPS: the oldest model update's
    # before_vps if the venture has ever been updated, otherwise the
    # venture's own current VPS (honest, since nothing has changed since
    # creation -- see this endpoint's own docstring).
    initial_vps = model_updates[0]["before_vps"] if model_updates else (venture.get("model_result") or {}).get("vps")
    events.append(VentureHistoryEvent(
        event_type="venture_created",
        occurred_at=venture["created_at"],
        title="Venture created",
        after_vps=initial_vps,
    ))

    events.sort(key=lambda e: e.occurred_at, reverse=True)

    actions_completed = sum(1 for m in missions if m.get("completed_at") is not None)

    strongest_improvement = None
    positive_changes = [c for c in all_category_changes if c.before is not None and c.after is not None and c.after > c.before]
    if positive_changes:
        strongest_improvement = max(positive_changes, key=lambda c: c.after - c.before)

    return VentureHistoryResponse(
        events=events,
        current_vps=(venture.get("model_result") or {}).get("vps"),
        started_at=venture["created_at"],
        actions_completed=actions_completed,
        model_updates_count=len(model_updates),
        strongest_improvement=strongest_improvement,
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Phase 31 -- Venture -> Startup Graduation V1.
#
# The founder must explicitly choose to graduate -- nothing here ever
# runs from a background job, a VPS threshold, or any other automatic
# trigger. Both endpoints below sit behind the exact same
# _require_owned_venture() every other /ventures/{venture_id}/* endpoint
# uses (RequireAuth + an owner-scoped lookup that 404s for "doesn't
# exist" and "belongs to someone else" identically, per that function's
# own docstring).
#
# GRADUATION NEVER FABRICATES SPS/VPS DATA: creating a startup+membership
# here does not create, or imply the existence of, any analysis row --
# get_founder_startup_workspace() already renders a membership-only,
# zero-analysis startup correctly (methodology/created_at stay None, per
# that function's own docstring), so the founder lands on a real, honest
# "not yet analyzed" workspace, never a placeholder score. VPS itself
# (compute_vps(), venture_missions, venture_model_updates) is completely
# untouched by either endpoint below -- grep confirms neither imports nor
# calls anything from vps_scoring.py/vps_guidance.py.
# ---------------------------------------------------------------------------


@app.post("/ventures/{venture_id}/graduation/prompt-shown")
def log_graduation_prompt_shown(
    venture_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    """
    Part 14: fired once, client-side, when VentureGraduation.tsx actually
    renders the ELIGIBLE, prominent suggestion variant for this venture
    (never the quiet manual-only link, never a re-render of the same
    state) -- same "server decides every field from the URL path and auth
    context" pattern as log_snapshot_link_copied().
    """
    _require_owned_venture(current_user, venture_id)
    _log_event_safe("graduation_prompt_shown", user_id=current_user.user_id, venture_id=venture_id)
    return {"logged": True}


@app.post("/ventures/{venture_id}/graduation/started")
def log_graduation_started(
    venture_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    """Part 14: fired once, client-side, when the founder opens
    GraduateVentureReview (the review-before-create screen) -- distinct
    from venture_graduated, which only fires once the founder actually
    confirms and the row is persisted. A founder who opens the review and
    backs out logs this event and nothing else."""
    _require_owned_venture(current_user, venture_id)
    _log_event_safe("graduation_started", user_id=current_user.user_id, venture_id=venture_id)
    return {"logged": True}


@app.get("/ventures/{venture_id}/graduation", response_model=VentureGraduationStatus)
def get_venture_graduation_status(
    venture_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    _require_owned_venture(current_user, venture_id)

    graduation = get_venture_graduation_for_owner(current_user.user_id, venture_id)

    if graduation is None:
        return VentureGraduationStatus(graduated=False)

    return VentureGraduationStatus(
        graduated=True,
        startup_id=graduation["startup_id"],
        startup_name=graduation["startup_name"],
        connected_existing_startup=graduation["connected_existing_startup"],
        graduated_at=graduation["created_at"],
    )


@app.post("/ventures/{venture_id}/graduate", response_model=GraduateVentureResponse)
def graduate_venture(
    venture_id: int,
    request: GraduateVentureRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    """
    Idempotent by construction (Part 12's adversarial duplicate-protection
    requirement): a double-click, two parallel tabs, a refreshed page
    resubmitting, or a direct repeated API call for the SAME venture_id
    all land on venture_graduations' own UNIQUE(venture_id) constraint --
    create_venture_graduation() returns None on a conflict rather than
    raising, and this endpoint responds with the EXISTING graduation
    (never a second startup, never an error) exactly as if the caller had
    called GET .../graduation instead. This makes "double-click" and
    "already graduated, POST again" behave identically -- both are safe.

    Two resolution paths, matching GraduateVentureRequest's own docstring:

    - connect_existing_startup_id set (Part 13): ownership is checked
      directly (a membership row must already exist for this exact user +
      startup_id) -- the ONLY safe case for "connect existing", never
      fuzzy name matching, never AI, never automatic merge. A non-member
      or nonexistent id 404s with the same "not found" framing
      RequireStartupMember itself uses, so this can't be used to probe
      which startup ids exist.
    - otherwise: resolve_startup_for_graduation() either creates a fresh
      startup or raises StartupNameCollisionError (a startup with this
      exact name exists and the founder does not already own it) --
      surfaced as 409 Conflict, never silently attached to a stranger's
      company.

    Membership is granted via create_venture_graduation()'s own reuse of
    create_startup_claim() + approve_startup_claim() (self-approval) --
    see that function's docstring in app/database/db.py for the full
    provenance reasoning. This endpoint never inserts into
    startup_memberships itself (test_no_new_membership_write_path would
    fail if it did).

    Phase 31A -- Graduation Integrity Hardening: the write sequence
    (startup + its claim atomically -> membership -> venture_graduations
    linkage, in that order) is specifically designed so that a crash at
    ANY point still converges to one correct Venture <-> Startup
    relationship on a plain retry of this same endpoint -- never an
    orphan startup, never a permanent lockout, never a venture that reads
    as graduated without real access. See resolve_startup_for_graduation()
    and create_venture_graduation()'s own docstrings in app/database/db.py
    for the full failure-mode analysis, and
    app/tests/test_venture_graduation.py's "Phase 31A" section for the
    tests proving it.
    """
    _require_owned_venture(current_user, venture_id)

    existing = get_venture_graduation_for_owner(current_user.user_id, venture_id)
    if existing is not None:
        return GraduateVentureResponse(
            startup_id=existing["startup_id"],
            startup_name=existing["startup_name"],
            connected_existing_startup=existing["connected_existing_startup"],
        )

    pending_claim_id: int | None = None

    if request.connect_existing_startup_id is not None:
        is_member = user_has_startup_membership(
            current_user.user_id, request.connect_existing_startup_id
        )

        if not is_member:
            raise HTTPException(status_code=404, detail="Startup not found.")

        startup_id = request.connect_existing_startup_id
        connected_existing_startup = True
    else:
        try:
            startup_id, connected_existing_startup, pending_claim_id = resolve_startup_for_graduation(
                request.company_name, current_user.user_id
            )
        except StartupNameCollisionError as error:
            raise HTTPException(status_code=409, detail=str(error))

    try:
        create_venture_graduation(
            venture_id=venture_id,
            startup_id=startup_id,
            user_id=current_user.user_id,
            trigger=request.trigger,
            connected_existing_startup=connected_existing_startup,
            fields_transferred_count=request.fields_transferred_count,
            pending_claim_id=pending_claim_id,
        )
    except StartupAlreadyGraduatedError as error:
        # Database invariant #3 (Phase 31A): reachable only via "connect
        # an existing startup" -- that startup already has a DIFFERENT
        # venture's graduation link. Never resolved automatically; the
        # founder must pick a different startup to connect, or leave this
        # venture ungraduated.
        raise HTTPException(status_code=409, detail=str(error))

    startup_name = get_venture_graduation_for_owner(current_user.user_id, venture_id)["startup_name"]

    # Part 14: fires only after the graduation row is actually persisted
    # (or the connect-existing path completes) -- never on merely opening
    # the review screen (that's graduation_started, logged client-side --
    # see VentureGraduation.tsx). No venture/startup content in metadata,
    # matching every other analytics call site's "closed vocabulary
    # values only" discipline.
    _log_event_safe(
        "venture_graduated",
        user_id=current_user.user_id,
        venture_id=venture_id,
        metadata={
            "trigger": request.trigger,
            "connected_existing_startup": connected_existing_startup,
        },
    )

    return GraduateVentureResponse(
        startup_id=startup_id,
        startup_name=startup_name,
        connected_existing_startup=connected_existing_startup,
    )


@app.post("/ventures/{venture_id}/graduation/startup-opened")
def log_startup_opened_from_venture(
    venture_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    """
    Part 14: fired only from the Venture-side "Open Startup Profile ->"
    control a graduated venture shows (never from the Startup side, and
    never from any other Analyze/Founder Workspace navigation) -- mirrors
    log_snapshot_link_copied()'s own "server decides every field from the
    URL path and auth context, client sends nothing" pattern. Requires an
    actual graduation row to exist (same _require_owned_venture ownership
    gate as every other /ventures/{id}/* endpoint, plus this explicit
    existence check) so a stray call for a never-graduated venture can't
    pollute the count.
    """
    _require_owned_venture(current_user, venture_id)

    if get_venture_graduation_for_owner(current_user.user_id, venture_id) is not None:
        _log_event_safe("startup_opened_from_venture", user_id=current_user.user_id, venture_id=venture_id)

    return {"logged": True}


# Phase 10.8 -- Pitch Deck Coach V1. Deliberately separate from POST
# /analyze in every way that matters (see app/ai/pitch_deck_coaching.py's
# own module docstring for the full investigation/boundary record): this
# never calls run_due_diligence(), never touches Methodology v2/SPS/VPS,
# and a PitchDeckReview can never become a Startup/Analysis/modeled
# venture. Authorization is ownership-only (RequireAuth + a
# user_id-scoped query), never RequireStartupMember -- a student with
# only a deck and no startup must be able to use this (Part 19).
# ---------------------------------------------------------------------------

# One review makes exactly one LLM call (materially cheaper than the
# six-pillar canonical pipeline /analyze protects) -- see
# count_recent_pitch_deck_reviews()'s own docstring in app/database/db.py
# for why this reuses that module's count-based cost control rather than
# its full concurrency-lock/fingerprint machinery, which this phase's own
# required test list (Part 25) does not call for.
PITCH_DECK_REVIEW_DAILY_CAP = 15


def _require_owned_pitch_deck_review(current_user: AuthenticatedUser, review_id: int) -> dict:
    review = get_pitch_deck_review_for_user(current_user.user_id, review_id)

    if review is None:
        raise HTTPException(status_code=404, detail="Pitch deck review not found.")

    return review


def _pitch_deck_review_response(saved: dict) -> PitchDeckReviewResponse:
    return PitchDeckReviewResponse(id=saved["id"], created_at=saved["created_at"], **saved["review"])


@app.post("/pitch-deck-reviews", response_model=PitchDeckReviewResponse)
def create_pitch_deck_review_endpoint(
    pdf: UploadFile = File(...),
    current_user: AuthenticatedUser = RequireAuth,
):
    if not pdf.filename or not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    if count_recent_pitch_deck_reviews(current_user.user_id, USAGE_WINDOW_HOURS) >= PITCH_DECK_REVIEW_DAILY_CAP:
        raise HTTPException(
            status_code=429,
            detail=(
                f"You've reached the current limit of {PITCH_DECK_REVIEW_DAILY_CAP} "
                f"pitch deck reviews per {USAGE_WINDOW_HOURS} hours. Please try again later."
            ),
        )

    # Reuses the exact same bounded, in-memory-only upload reader /analyze
    # already uses -- see _read_pdf_upload_sync()'s own docstring above.
    # No new PDF I/O path; no PDF security helper duplicated or weakened.
    try:
        pdf_bytes = _read_pdf_upload_sync(pdf)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as _exc:
        traceback.print_exc()
        capture_exception(_exc)
        raise HTTPException(
            status_code=400,
            detail="That PDF could not be read. Please check the file and try again.",
        )

    try:
        pages = extract_pages_from_pdf(pdf_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as _exc:
        traceback.print_exc()
        capture_exception(_exc)
        raise HTTPException(
            status_code=400,
            detail="That PDF could not be read. Please check the file and try again.",
        )

    try:
        review = generate_pitch_deck_review(pages, pdf.filename)
    except PitchDeckCoachingError:
        traceback.print_exc()
        raise HTTPException(
            status_code=502,
            detail="We couldn't review that pitch deck right now. Please try again.",
        )
    except Exception as _exc:
        traceback.print_exc()
        capture_exception(_exc)
        raise HTTPException(
            status_code=502,
            detail="We couldn't review that pitch deck right now. Please try again.",
        )

    try:
        review_id = create_pitch_deck_review(
            user_id=current_user.user_id,
            deck_filename=review["deck_filename"],
            page_count=review["page_count"],
            readiness_label=review["readiness_label"],
            review=review,
        )
    except Exception as _exc:
        traceback.print_exc()
        capture_exception(_exc)
        raise HTTPException(
            status_code=500,
            detail="Your review completed but could not be saved. Please try again.",
        )

    saved = get_pitch_deck_review_for_user(current_user.user_id, review_id)
    return _pitch_deck_review_response(saved)


@app.get("/pitch-deck-reviews", response_model=list[PitchDeckReviewSummary])
def list_pitch_deck_reviews(current_user: AuthenticatedUser = RequireAuth):
    reviews = list_pitch_deck_reviews_for_user(current_user.user_id)

    return [
        PitchDeckReviewSummary(
            id=review["id"],
            deck_filename=review["deck_filename"],
            readiness_label=review["readiness_label"],
            created_at=review["created_at"],
        )
        for review in reviews
    ]


@app.get("/pitch-deck-reviews/{review_id}", response_model=PitchDeckReviewResponse)
def get_pitch_deck_review_endpoint(
    review_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    saved = _require_owned_pitch_deck_review(current_user, review_id)
    return _pitch_deck_review_response(saved)


# ---------------------------------------------------------------------------
# Phase 7.1A -- Startup Claim & Membership backend lifecycle.
#
# CORE INVARIANT: startup_memberships represents actual authorized
# relationships. A pending, rejected, or cancelled claim NEVER creates a
# membership -- the only endpoint below that can possibly result in a new
# startup_memberships row is approve_my_claim_admin_action (the admin
# approval action), which delegates to approve_startup_claim(), the one
# function in this codebase allowed to write that table (see its own
# docstring in app/database/db.py).
#
# user_id is derived exclusively from RequireAuth/current_user.user_id on
# every founder-facing endpoint below -- never accepted from a path,
# query, or body parameter. Admin endpoints are gated by RequireAdmin,
# which itself is built on the same unchanged JWT verification (see
# app/auth.py) plus a server-side ADMIN_USER_IDS allowlist check.
# ---------------------------------------------------------------------------

@app.post("/startup-claims", response_model=StartupClaimSubmissionResponse)
def submit_startup_claim(
    request: CreateStartupClaimRequest,
    current_user: AuthenticatedUser = RequireAuth,
):
    try:
        claim_id = create_startup_claim(
            user_id=current_user.user_id,
            startup_id=request.startup_id,
            justification=request.justification,
            contact_email=request.contact_email,
        )
    except StartupNotFoundError:
        raise HTTPException(status_code=404, detail="Startup not found.")
    except AlreadyMemberError:
        raise HTTPException(
            status_code=409,
            detail="You already have access to this startup -- no claim is needed.",
        )
    except DuplicatePendingClaimError:
        raise HTTPException(
            status_code=409,
            detail="You already have a pending claim for this startup.",
        )
    except Exception as _exc:
        traceback.print_exc()
        capture_exception(_exc)
        raise HTTPException(
            status_code=500,
            detail="Your claim could not be submitted. Please try again.",
        )

    return StartupClaimSubmissionResponse(
        id=claim_id, startup_id=request.startup_id, status="pending"
    )


@app.get("/me/startup-claims", response_model=list[MyStartupClaim])
def list_my_startup_claims(current_user: AuthenticatedUser = RequireAuth):
    return list_startup_claims_for_user(current_user.user_id)


@app.get("/me/startup-claims/{startup_id}", response_model=StartupClaimStatus | None)
def get_my_startup_claim_status(
    startup_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    """Smallest useful helper for Phase 7.1B's 'Claim this startup'
    control -- the caller's own most recent claim for this one startup,
    or null if they've never claimed it. Never reveals anyone else's
    claim status for the same startup."""
    status = get_startup_claim_status_for_user(current_user.user_id, startup_id)

    if status is None:
        return None

    return StartupClaimStatus(
        claim_id=status["id"],
        status=status["status"],
        verification_method=status["verification_method"],
        submitted_at=status["submitted_at"],
        reviewed_at=status["reviewed_at"],
        rejection_reason=status["rejection_reason"],
    )


@app.post("/me/startup-claims/{claim_id}/cancel", response_model=StartupClaimActionResponse)
def cancel_my_startup_claim(
    claim_id: int,
    current_user: AuthenticatedUser = RequireAuth,
):
    cancelled = cancel_startup_claim(current_user.user_id, claim_id)

    if not cancelled:
        # Same non-leaking shape as every other user-scoped resource in
        # this codebase: "doesn't exist", "belongs to someone else", and
        # "isn't pending anymore" are all indistinguishable from the
        # caller's perspective.
        raise HTTPException(status_code=404, detail="Claim not found.")

    return StartupClaimActionResponse(claim_id=claim_id, status="cancelled")


@app.get("/admin/startup-claims", response_model=list[AdminStartupClaim])
def list_admin_startup_claims(current_user: AuthenticatedUser = RequireAdmin):
    return list_pending_startup_claims_for_admin()


@app.post("/admin/startup-claims/{claim_id}/approve", response_model=StartupClaimActionResponse)
def approve_admin_startup_claim(
    claim_id: int,
    current_user: AuthenticatedUser = RequireAdmin,
):
    result = approve_startup_claim(claim_id, current_user.user_id)

    if result is None:
        raise HTTPException(
            status_code=409,
            detail="This claim is not currently pending (it may not exist, or has already been reviewed).",
        )

    return StartupClaimActionResponse(claim_id=claim_id, status="approved")


@app.post("/admin/startup-claims/{claim_id}/reject", response_model=StartupClaimActionResponse)
def reject_admin_startup_claim(
    claim_id: int,
    request: RejectStartupClaimRequest,
    current_user: AuthenticatedUser = RequireAdmin,
):
    rejected = reject_startup_claim(claim_id, current_user.user_id, request.rejection_reason)

    if not rejected:
        raise HTTPException(
            status_code=409,
            detail="This claim is not currently pending (it may not exist, or has already been reviewed).",
        )

    return StartupClaimActionResponse(claim_id=claim_id, status="rejected")


# ---------------------------------------------------------------------------
# Phase 7.1C -- Founder Membership Authorization Foundation. Read-only:
# get_startup_memberships_for_user() derives every row exclusively from
# startup_memberships (see that function's own docstring) -- never from
# startup_claims, saved_startups, or modeled_ventures. This is the
# intended entry point for a future /founder surface (Phase 7.2): "which
# canonical startups does this authenticated user legitimately belong
# to?" user_id is derived exclusively from RequireAuth/current_user.user_id,
# never from a path, query, or body parameter, same discipline as every
# other /me/* endpoint above.
# ---------------------------------------------------------------------------

@app.get("/me/startups", response_model=list[MyStartupMembership])
def list_my_startups(current_user: AuthenticatedUser = RequireAuth):
    return get_startup_memberships_for_user(current_user.user_id)


# ---------------------------------------------------------------------------
# Phase 7.2 -- Founder Workspace V1. RequireStartupMember (app/auth.py)
# resolves startup_id from this route's own path parameter and 404s
# before this function body ever runs if the caller has no live
# startup_memberships row for it -- never authorized by startup_claims,
# saved_startups, modeled_ventures, or anything client-supplied. This is
# the only startup-scoped Founder Workspace endpoint in V1.
# ---------------------------------------------------------------------------

@app.get("/founder/startups/{startup_id}", response_model=FounderStartupWorkspace)
def get_founder_startup(
    startup_id: int,
    current_user: AuthenticatedUser = RequireStartupMember,
):
    workspace = get_founder_startup_workspace(startup_id, current_user.user_id)

    if workspace is None:
        # Should be unreachable once RequireStartupMember has already
        # passed (a membership row can't reference a nonexistent
        # startups.id, per that table's own FK) -- kept as a clean 404
        # rather than a 500 in case that ever stops being true.
        raise HTTPException(status_code=404, detail="Startup not found.")

    return workspace


# ---------------------------------------------------------------------------
# Phase 7.3 -- Founder Progress & Improvement V1. Same RequireStartupMember
# gate as GET /founder/startups/{startup_id} above -- every endpoint below
# 404s before its body runs if the caller has no live startup_memberships
# row for this exact startup_id, never authorized by startup_claims,
# saved_startups, modeled_ventures, or anything client-supplied.
#
# Shared plan, not per-member (Part 11): none of these endpoints filter
# by current_user.user_id -- any verified member of the startup sees and
# can act on every action in it. created_by_user_id (set from
# current_user.user_id, never accepted from the request body) is
# provenance only.
#
# founder_actions is pure workflow state -- no endpoint here ever touches
# analyses, methodology, startup_intelligence_score, or
# startup_memberships. See app/database/db.py's own Phase 7.3 section for
# the full boundary statement and app/tests/test_founder_actions.py for
# the code-level audit.
#
# No separate GET .../suggested-actions endpoint exists: the six pillars'
# real recommendations are already present in GET /founder/startups/
# {startup_id}'s own `methodology` field (Phase 7.2), and the frontend
# derives suggested actions from that response client-side -- identical
# in spirit to how PrioritiesSection's "Top Priorities" already ranks by
# weakest pillar. Adding a second endpoint to return the same data a
# different way would duplicate, not simplify, this surface.
# ---------------------------------------------------------------------------

@app.get("/founder/startups/{startup_id}/actions", response_model=list[FounderAction])
def list_founder_actions(
    startup_id: int,
    current_user: AuthenticatedUser = RequireStartupMember,
):
    return list_founder_actions_for_startup(startup_id)


@app.post("/founder/startups/{startup_id}/actions", response_model=FounderAction)
def create_founder_action_endpoint(
    startup_id: int,
    request: CreateFounderActionRequest,
    current_user: AuthenticatedUser = RequireStartupMember,
):
    if request.related_pillar is not None and request.related_pillar not in FOUNDER_ACTION_PILLARS:
        raise HTTPException(
            status_code=400,
            detail=f"related_pillar must be one of {sorted(FOUNDER_ACTION_PILLARS)} or omitted.",
        )

    return create_founder_action(
        startup_id=startup_id,
        created_by_user_id=current_user.user_id,
        title=request.title.strip(),
        description=(request.description.strip() if request.description else None),
        related_pillar=request.related_pillar,
        source=request.source,
    )


@app.patch("/founder/startups/{startup_id}/actions/{action_id}", response_model=FounderAction)
def update_founder_action_status_endpoint(
    startup_id: int,
    action_id: int,
    request: UpdateFounderActionStatusRequest,
    current_user: AuthenticatedUser = RequireStartupMember,
):
    updated = update_founder_action_status(startup_id, action_id, request.status)

    if updated is None:
        # Same non-leaking shape as every other startup/claim-scoped
        # resource in this codebase: "doesn't exist" and "belongs to a
        # different startup" are indistinguishable from the caller's
        # perspective.
        raise HTTPException(status_code=404, detail="Action not found.")

    return updated


# ---------------------------------------------------------------------------
# Phase 7.4 -- Founder Evidence + Milestones V1. Same RequireStartupMember
# gate as every other Founder Workspace endpoint above -- every route
# below 404s before its body runs if the caller has no live
# startup_memberships row for this exact startup_id, never authorized by
# startup_claims, saved_startups, modeled_ventures, or anything
# client-supplied.
#
# Shared plan (Part 11, same decision as Phase 7.3): none of these
# endpoints filter by current_user.user_id -- any verified member of the
# startup sees and can act on every update/milestone in it.
# created_by_user_id (set from current_user.user_id, never accepted from
# the request body) is provenance only.
#
# founder_updates/startup_milestones are pure founder-reported record --
# no endpoint here ever touches analyses, methodology,
# startup_intelligence_score, or startup_memberships. See
# app/database/db.py's own Phase 7.4 section for the full boundary
# statement and app/tests/test_founder_updates.py /
# test_startup_milestones.py for the code-level audits.
# ---------------------------------------------------------------------------

@app.get("/founder/startups/{startup_id}/updates", response_model=list[FounderUpdate])
def list_founder_updates(
    startup_id: int,
    current_user: AuthenticatedUser = RequireStartupMember,
):
    return list_founder_updates_for_startup(startup_id)


@app.post("/founder/startups/{startup_id}/updates", response_model=FounderUpdate)
def create_founder_update_endpoint(
    startup_id: int,
    request: CreateFounderUpdateRequest,
    current_user: AuthenticatedUser = RequireStartupMember,
):
    if request.related_pillar is not None and request.related_pillar not in FOUNDER_UPDATE_PILLARS:
        raise HTTPException(
            status_code=400,
            detail=f"related_pillar must be one of {sorted(FOUNDER_UPDATE_PILLARS)} or omitted.",
        )

    return create_founder_update(
        startup_id=startup_id,
        created_by_user_id=current_user.user_id,
        update_type=request.update_type,
        title=request.title.strip(),
        description=(request.description.strip() if request.description else None),
        related_pillar=request.related_pillar,
        occurred_at=request.occurred_at,
        metric_name=request.metric_name,
        metric_value=request.metric_value,
        metric_unit=request.metric_unit,
    )


@app.patch("/founder/startups/{startup_id}/updates/{update_id}", response_model=FounderUpdate)
def update_founder_update_endpoint(
    startup_id: int,
    update_id: int,
    request: UpdateFounderUpdateRequest,
    current_user: AuthenticatedUser = RequireStartupMember,
):
    if request.related_pillar is not None and request.related_pillar not in FOUNDER_UPDATE_PILLARS:
        raise HTTPException(
            status_code=400,
            detail=f"related_pillar must be one of {sorted(FOUNDER_UPDATE_PILLARS)} or omitted.",
        )

    updated = update_founder_update(
        startup_id=startup_id,
        update_id=update_id,
        update_type=request.update_type,
        title=request.title.strip(),
        description=(request.description.strip() if request.description else None),
        related_pillar=request.related_pillar,
        occurred_at=request.occurred_at,
        metric_name=request.metric_name,
        metric_value=request.metric_value,
        metric_unit=request.metric_unit,
    )

    if updated is None:
        raise HTTPException(status_code=404, detail="Update not found.")

    return updated


@app.get("/founder/startups/{startup_id}/milestones", response_model=list[StartupMilestone])
def list_startup_milestones(
    startup_id: int,
    current_user: AuthenticatedUser = RequireStartupMember,
):
    return list_startup_milestones_for_startup(startup_id)


@app.post("/founder/startups/{startup_id}/milestones", response_model=StartupMilestone)
def create_startup_milestone_endpoint(
    startup_id: int,
    request: CreateMilestoneRequest,
    current_user: AuthenticatedUser = RequireStartupMember,
):
    if request.related_pillar is not None and request.related_pillar not in MILESTONE_PILLARS:
        raise HTTPException(
            status_code=400,
            detail=f"related_pillar must be one of {sorted(MILESTONE_PILLARS)} or omitted.",
        )

    return create_startup_milestone(
        startup_id=startup_id,
        created_by_user_id=current_user.user_id,
        title=request.title.strip(),
        description=(request.description.strip() if request.description else None),
        related_pillar=request.related_pillar,
        target_date=request.target_date,
    )


@app.patch("/founder/startups/{startup_id}/milestones/{milestone_id}", response_model=StartupMilestone)
def update_startup_milestone_status_endpoint(
    startup_id: int,
    milestone_id: int,
    request: UpdateMilestoneStatusRequest,
    current_user: AuthenticatedUser = RequireStartupMember,
):
    updated = update_startup_milestone_status(startup_id, milestone_id, request.status)

    if updated is None:
        raise HTTPException(status_code=404, detail="Milestone not found.")

    return updated


# ---------------------------------------------------------------------------
# Phase 8 -- Fundraising Readiness V1. Same RequireStartupMember gate as
# every other Founder Workspace endpoint -- 404s before its body runs if
# the caller has no live startup_memberships row for this exact
# startup_id, never authorized by startup_claims, saved_startups,
# modeled_ventures, or anything client-supplied. Fundraising preparation
# is private founder information; this is deliberately not a public
# endpoint.
#
# Reuses get_founder_startup_workspace() (Phase 7.2) unchanged rather
# than a new query -- readiness is computed fresh from the SAME canonical
# methodology that endpoint already reads, never a second source of
# truth, never persisted (see app/ai/fundraising_readiness.py's own
# module docstring for the persistence decision). This function performs
# no scoring itself -- assess_fundraising_readiness() is pure,
# deterministic arithmetic over already-computed fields; nothing here
# calls an LLM, writes methodology, or touches startup_memberships.
# ---------------------------------------------------------------------------

@app.get("/founder/startups/{startup_id}/fundraising", response_model=FundraisingReadinessResponse)
def get_fundraising_readiness(
    startup_id: int,
    current_user: AuthenticatedUser = RequireStartupMember,
):
    workspace = get_founder_startup_workspace(startup_id, current_user.user_id)

    if workspace is None:
        raise HTTPException(status_code=404, detail="Startup not found.")

    methodology = workspace["methodology"]
    assessment = assess_fundraising_readiness(methodology)

    current_sps = methodology.get("startup_intelligence_score") if methodology is not None else None
    created_at = workspace["created_at"]

    return FundraisingReadinessResponse(
        startup_id=workspace["startup_id"],
        canonical_name=workspace["canonical_name"],
        has_canonical_analysis=assessment.has_canonical_analysis,
        stage_label=assessment.stage_label,
        stage_recognized=assessment.stage_recognized,
        readiness_score=assessment.readiness_score,
        readiness_band=assessment.readiness_band,
        pillar_readiness=[
            PillarReadinessOut(
                pillar=p.pillar,
                label=p.label,
                score=p.score,
                confidence=p.confidence,
                evidence_coverage=p.evidence_coverage,
                weight=p.weight,
                readiness_contribution=p.readiness_contribution,
                top_strength=p.top_strength,
                top_weakness=p.top_weakness,
            )
            for p in assessment.pillar_readiness
        ],
        gaps=[
            ReadinessGapOut(
                category=g.category,
                pillar=g.pillar,
                issue=g.issue,
                why_it_matters=g.why_it_matters,
                recommended_next_step=g.recommended_next_step,
                source_text=g.source_text,
            )
            for g in assessment.gaps
        ],
        investor_questions=assessment.investor_questions,
        checklist=[
            ChecklistItemOut(category=c.category, status=c.status, note=c.note)
            for c in assessment.checklist
        ],
        has_pitch_deck=assessment.has_pitch_deck,
        pitch_deck_note=assessment.pitch_deck_note,
        current_sps=current_sps,
        analyzed_at=created_at.isoformat() if created_at is not None else None,
        linked_venture_id=workspace["linked_venture_id"],
    )


@app.put("/analyses/{analysis_id}")
def update_saved_analysis(
    analysis_id: int,
    request: UpdateAnalysisRequest,
    current_user: AuthenticatedUser = RequireAdmin,
):
    updated_count = update_analysis(
        analysis_id,
        request.company_text,
        request.summary,
        request.risk_analysis,
        request.competitor_analysis,
        request.memo,
        request.structured_analysis,
        request.investment_score,
        request.founder_analysis,
        request.market_analysis,
        request.sources,
        request.traction_analysis
    )

    if updated_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Analysis not found"
        )

    return {
        "message": "Analysis updated successfully"
    }

@app.delete("/analyses/{analysis_id}")
def delete_saved_analysis(analysis_id: int, current_user: AuthenticatedUser = RequireAdmin):
    deleted_count = delete_analysis(analysis_id)

    if deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Analysis not found"
        )
    
    return {
        "message": "Analysis deleted successfully"
    }

# Unified Multi-Source Analyze Startup: three maxed-out sources joined
# together could otherwise be far larger than any single source was ever
# bounded to (company_text alone is capped at MAX_COMPANY_TEXT_LENGTH,
# but website/PDF extraction have their own separate byte-level caps with
# no shared character-count ceiling) -- this bounds the ASSEMBLED result,
# after every individual source has already validated on its own.
MAX_ASSEMBLED_TEXT_LENGTH = 150_000


def _read_pdf_upload_sync(file: UploadFile) -> bytes:
    """
    Sync counterpart to the now-unused async _read_pdf_upload() (below) --
    originally written for use inside POST /analyze's sync (non-async)
    path operation function, see analyze_unified()'s concurrency comment
    for why, and reused as of Phase 10.1A by /analyze-pdf as well (also
    converted to a sync `def`; see that endpoint's own comment). Reads
    the upload's underlying file object directly (UploadFile.file, a
    plain SpooledTemporaryFile) in bounded chunks -- no `await` needed
    here, since it's FastAPI's automatic threadpool dispatch for a sync route
    that keeps this off the event loop, not anything async in this
    function itself. Still fully in-memory, still no temporary files.
    """
    chunks: list[bytes] = []
    total = 0

    while True:
        chunk = file.file.read(64 * 1024)

        if not chunk:
            break

        total += len(chunk)

        if total > MAX_PDF_BYTES:
            raise PdfExtractionError(
                f"That PDF is too large to analyze (max "
                f"{MAX_PDF_BYTES // (1024 * 1024)} MB)."
            )

        chunks.append(chunk)

    return b"".join(chunks)


@app.post("/analyze", response_model=StartupAnalysisResponse)
def analyze_unified(
    website_url: str | None = Form(None),
    company_text: str | None = Form(None),
    pdf: UploadFile | None = File(None),
    # Phase 7.2.1 -- Deterministic Founder Re-analysis: OPTIONAL. Absent
    # (None) on every normal/public analysis -- that path is completely
    # unchanged, see below and save_analysis()'s own docstring. When
    # present, this becomes the authoritative canonical identity for the
    # resulting analysis (Founder Workspace's "Re-analyze"), gated by the
    # membership check immediately below -- never trusted merely because
    # the client supplied it.
    startup_id: int | None = Form(None),
    current_user: AuthenticatedUser = RequireAuth,
):
    # SIE Authentication Phase 2: requires a valid Clerk-authenticated
    # user -- RequireAuth resolves before this function body runs, so an
    # unauthenticated request is rejected with a clean 401 before any
    # extraction/pipeline work (and therefore before any paid OpenAI/
    # Tavily cost) ever happens. current_user is intentionally unused
    # beyond that when startup_id is absent: authentication means "this
    # user exists" (see get_or_create_user()'s docstring), never "this
    # user owns this startup" -- no startup_membership is created here or
    # anywhere in this function, by design, regardless of startup_id.
    #
    # Unified Multi-Source Analyze Startup: website, pitch deck, and
    # user-provided text are evidence SOURCES feeding ONE canonical SIE
    # analysis, not separate mutually-exclusive analysis products (see
    # the Phase 1 design report and the Phase 2 product decision this
    # implements). As of Phase 10.1B this is the ONLY paid analysis entry
    # point -- /analyze-startup, /analyze-website, and /analyze-pdf were
    # removed (zero frontend/product consumers, confirmed by repository
    # search) so there is exactly one HTTP surface to protect, not four.
    # The underlying extraction helpers those routes used
    # (extract_text_from_website, extract_text_from_pdf,
    # _read_pdf_upload_sync) and their request models (WebsiteAnalysisRequest,
    # StartupAnalysisRequest) are unchanged and still used directly below.
    #
    # Deliberately a sync `def`, not `async def`: FastAPI/Starlette
    # automatically runs a sync path operation in a worker thread, which
    # is what keeps the multi-minute pipeline call below from blocking
    # the event loop and starving concurrent requests (GET /health,
    # /analytics, ...).
    #
    # Phase 7.2.1: the founder-targeted membership check runs FIRST --
    # before URL/PDF validation, before any extraction, before the
    # pipeline -- so an unauthorized or invalid startup_id fails closed
    # with zero side effects and zero pipeline cost, per that phase's own
    # "do not run the expensive analysis pipeline" requirement.
    # require_startup_member() is called directly as a plain function
    # (not via its usual Depends() wiring, which only resolves startup_id
    # from a route's own PATH parameter -- this route has none, since
    # startup_id is optional here) -- same function, same
    # membership-only check, same non-leaking 404, as every other
    # RequireStartupMember caller; reused, not reimplemented.
    if startup_id is not None:
        require_startup_member(startup_id=startup_id, current_user=current_user)

    website_url = website_url.strip() if website_url else None
    company_text = company_text.strip() if company_text else None
    has_pdf = pdf is not None and bool(pdf.filename)

    if not website_url and not company_text and not has_pdf:
        raise HTTPException(
            status_code=400,
            detail=(
                "Provide at least one of: company website, pitch deck, or "
                "company information."
            ),
        )

    # Phase 10.1B: cheap, zero-I/O-beyond-reading-the-upload format
    # validation happens BEFORE the usage-protection gate below, so a
    # request with an obviously malformed URL, a non-PDF upload, or
    # oversized text never consumes a usage-cap slot or trips the
    # duplicate-cooldown/concurrency-lock checks for something that was
    # never going to run anyway.
    validated_url = None

    if website_url:
        try:
            validated_url = WebsiteAnalysisRequest(url=website_url)
        except PydanticValidationError:
            raise HTTPException(
                status_code=400,
                detail="Website URL must start with http:// or https://",
            )

    if has_pdf and not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400, detail="Only PDF files are supported."
        )

    if company_text:
        # Reuses StartupAnalysisRequest's own bound (MAX_COMPANY_TEXT_LENGTH)
        # rather than duplicating the number -- company_text here is a raw
        # Form field, not something Pydantic validates on the way in.
        try:
            StartupAnalysisRequest(company_text=company_text)
        except PydanticValidationError:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Additional company information must be no more than "
                    f"{MAX_COMPANY_TEXT_LENGTH:,} characters."
                ),
            )

    # Reads the raw upload now (bounded by MAX_PDF_BYTES, already-hardened
    # I/O -- see _read_pdf_upload_sync's own docstring) so its bytes are
    # available for the fingerprint below. This is deliberately NOT yet
    # extract_text_from_pdf() -- the actual (heavier, more failure-prone)
    # text-extraction step stays gated behind the usage-protection check
    # further down, per Part 5's "PDF extraction if reasonably avoidable."
    pdf_bytes = None

    if has_pdf:
        try:
            pdf_bytes = _read_pdf_upload_sync(pdf)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as _exc:
            traceback.print_exc()
            capture_exception(_exc)
            raise HTTPException(
                status_code=400,
                detail=(
                    "That PDF could not be read. Please check the file and "
                    "try again."
                ),
            )

    # -------------------------------------------------------------------
    # Phase 10.1B -- AI Cost + Analysis Abuse Protection. Everything from
    # here through begin_analysis_run() runs BEFORE website fetch, PDF
    # text extraction, and run_due_diligence() -- see
    # app/database/db.py's own module comment (right above
    # create_analysis_runs_table()) for the full design record: why a
    # Postgres partial unique index is the durability mechanism, why the
    # duplicate-cooldown check never applies to a founder-targeted
    # re-analysis, and why the daily cap counts started attempts.
    # -------------------------------------------------------------------
    fingerprint = compute_analysis_fingerprint(company_text, website_url, pdf_bytes)

    # Rapid-accidental-duplicate check (Part 4.B) -- deliberately skipped
    # entirely for a founder-targeted re-analysis (startup_id is not
    # None): re-running the same startup soon after a previous analysis
    # is Phase 7.2.1's own explicit, legitimate workflow, never a
    # duplicate to block. Never triggered by a FAILED prior run either
    # (has_recent_duplicate_completed_run only matches status='completed')
    # -- a user must always be able to immediately retry after a failure.
    if startup_id is None and has_recent_duplicate_completed_run(current_user.user_id, fingerprint):
        raise HTTPException(
            status_code=409,
            detail=(
                "You recently submitted this exact analysis. Please wait a "
                "few minutes before submitting it again."
            ),
        )

    # Beta usage cap (Part 4.C) -- counts every attempt (any status) in
    # the rolling window, applies equally to founder-targeted re-analysis.
    if count_recent_analysis_runs(current_user.user_id) >= DAILY_ANALYSIS_CAP:
        raise HTTPException(
            status_code=429,
            detail=(
                f"You've reached the current beta limit of {DAILY_ANALYSIS_CAP} "
                f"analyses per {USAGE_WINDOW_HOURS} hours. Please try again later."
            ),
        )

    # Same-user concurrency lock (Part 4.A) -- the ONLY place in this
    # codebase that inserts an analysis_runs row. A None return means a
    # genuinely active (non-stale) run already exists for this user;
    # begin_analysis_run() itself already expired any stale one first.
    run_id = begin_analysis_run(current_user.user_id, startup_id, fingerprint)

    if run_id is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "An analysis is already running for your account. Please "
                "wait for it to finish before starting another."
            ),
        )

    # Pessimistic default: only flipped to "completed" after save_analysis()
    # actually succeeds below. Every exit from this try block -- an
    # extraction failure, a pipeline failure, a persistence failure, or a
    # clean return -- reaches the finally clause exactly once, which is
    # what guarantees a crashed/failed request never leaves the user
    # permanently locked out (Part 5).
    run_status = "failed"

    try:
        # Product decision (unchanged from before Phase 10.1B): an
        # explicitly supplied source that fails extraction rejects the
        # WHOLE request before the expensive pipeline runs -- never
        # silently dropped in favor of whatever other sources succeeded.
        website_text = None
        pdf_text = None

        if validated_url is not None:
            try:
                website_text = extract_text_from_website(validated_url.url)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as _exc:
                traceback.print_exc()
                capture_exception(_exc)
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "That website could not be retrieved. Please check "
                        "the URL and try again."
                    ),
                )

        if pdf_bytes is not None:
            try:
                pdf_text = extract_text_from_pdf(pdf_bytes)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as _exc:
                traceback.print_exc()
                capture_exception(_exc)
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "That PDF could not be read. Please check the file "
                        "and try again."
                    ),
                )

        assembled_text = assemble_multi_source_text(
            website_text=website_text,
            pdf_text=pdf_text,
            user_text=company_text,
        )

        if len(assembled_text) > MAX_ASSEMBLED_TEXT_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=(
                    "The combined information from your sources is too long "
                    f"to analyze (max {MAX_ASSEMBLED_TEXT_LENGTH:,} characters "
                    "combined). Please shorten one or more sources."
                ),
            )

        # Unified Multi-Source Analyze Startup, Provenance: evidence_sources
        # is the real, non-mutually-exclusive record of what fed this
        # analysis -- activates the already-existing (previously dormant)
        # AnalysisContext.evidence_sources list field, no new field added.
        # public_research is always included since enrich_research() always
        # runs inside run_due_diligence() below. analysis_type stays a single
        # derived DISPLAY label only (backward compatible with the existing
        # Startup Profile badge) via the exact deterministic rule specified:
        # pitch_deck present wins, otherwise public. Neither field is read by
        # scoring, evidence extraction, or any pillar analysis.
        evidence_sources: list[str] = []

        if website_text:
            evidence_sources.append("website")

        if pdf_text:
            evidence_sources.append("pitch_deck")

        if company_text:
            evidence_sources.append("company_description")

        evidence_sources.append("public_research")

        analysis_type = "pitch_deck" if pdf_text else "public"

        try:
            results = run_due_diligence(
                assembled_text,
                analysis_type=analysis_type,
                evidence_sources=evidence_sources,
            )
        except Exception as _exc:
            traceback.print_exc()
            capture_exception(_exc)
            raise HTTPException(
                status_code=502,
                detail=(
                    "The analysis could not be completed. This can happen if a "
                    "research or AI provider is temporarily unavailable. Please "
                    "try again."
                ),
            )

        try:
            # Persist the assembled, labeled multi-source text as
            # company_text rather than picking one arbitrary source --
            # nothing supplied is silently left out of the stored record.
            save_analysis(
                company_text=assembled_text,
                summary=results["summary"],
                risk_analysis=results["risk_analysis"],
                competitor_analysis=results["competitor_analysis"],
                memo=results["memo"],
                structured_analysis=results["structured_analysis"],
                investment_score=results["investment_score"],
                founder_analysis=results["founder_analysis"].model_dump(),
                market_analysis=results["market_analysis"].model_dump(),
                sources=results["sources"],
                traction_analysis=results["traction_analysis"].model_dump(),
                methodology=results["sie_analysis"].model_dump(mode="json"),
                market_score=results["market_score"],
                team_score=results["team_score"],
                product_score=results["product_score"],
                competition_score=results["competition_score"],
                traction_score=results["traction_score"],
                financial_score=results["financial_score"],
                overall_score=results["overall_score"],
                recommendation=results["recommendation"],
                readiness_score=results["readiness_score"],
                readiness_summary=results["readiness_summary"],
                # Phase 7.2.1: None on every normal/public analysis (the
                # `if startup_id is not None` guard above is the only thing
                # that ever populates it, and only after that same value
                # already passed require_startup_member()) -- passing it
                # through here is what makes save_analysis() skip
                # get_or_create_startup() and attach directly to this exact
                # authorized canonical startup instead.
                startup_id=startup_id,
                # Portfolio Release Task 3B: every analysis this route
                # creates is attributed to the verified caller -- this
                # route is RequireAuth-gated, so current_user always exists
                # by the time this line runs, for both a normal and a
                # founder-targeted (startup_id is not None) submission.
                submitted_by_user_id=current_user.user_id,
            )
        except Exception as _exc:
            # Distinct from the pipeline failure above on purpose, same as
            # before Phase 10.1B: the (expensive, multi-minute) analysis DID
            # complete here -- only persisting it failed. save_score_history()
            # is deliberately not called here, for the same established
            # reason: Rankings/Search/Dashboard/SPS History all read
            # analyses.methodology JSONB directly, not the legacy
            # score_history table.
            traceback.print_exc()
            capture_exception(_exc)
            raise HTTPException(
                status_code=500,
                detail=(
                    "The analysis completed but could not be saved. Please try "
                    "again."
                ),
            )

        run_status = "completed"

        sie_analysis = results["sie_analysis"]

        return StartupAnalysisResponse(
            context=sie_analysis.context,
            startup_scorecard=sie_analysis.startup_scorecard,
            methodology=sie_analysis,
        )
    finally:
        finish_analysis_run(run_id, run_status)


# Phase 10.1B -- AI Cost + Analysis Abuse Protection. /analyze-startup,
# /analyze-pdf, and /analyze-website (and the async _read_pdf_upload()
# helper only /analyze-pdf ever called) were removed from here -- zero
# frontend/product consumers (confirmed by repository search), and each
# was a pure request-parsing wrapper around the exact same
# run_due_diligence() pipeline /analyze already runs, so removing them
# leaves one canonical paid analysis entry point to protect instead of
# four. Every reusable piece they depended on is untouched and still
# used directly by /analyze itself: extract_text_from_website,
# extract_text_from_pdf, _read_pdf_upload_sync, WebsiteAnalysisRequest,
# StartupAnalysisRequest. save_score_history() (only ever called from
# /analyze-startup) is also untouched -- GET /score-history/{company}
# still works for any pre-existing legacy data, it's simply never
# written to by any current code path, exactly as was already true
# before this phase (every other ingestion path already stopped calling
# it in favor of the canonical methodology JSONB).

# Phase 10.1A -- Critical Security Hardening. The three /migrate/* HTTP
# routes that used to live here (add-benchmarking-columns,
# add-company-name-column, add-readiness-columns) were removed: they were
# unauthenticated, unused by the frontend (confirmed by repository
# search), and fully redundant -- the exact same underlying functions
# (add_benchmarking_columns(), add_company_name_column(),
# add_readiness_columns(), imported above) already run unconditionally,
# idempotently, at process startup (see the migration sequence near the
# top of this file). Removing the routes closes an unauthenticated
# attack surface with zero loss of functionality; the migration helper
# functions themselves are untouched and still run on every startup.