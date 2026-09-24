# VentureGPS

VentureGPS is a full-stack startup intelligence platform designed to help founders and investors evaluate ventures, organize evidence, explore scenarios, and make more informed decisions.

The platform is powered by the Startup Intelligence Engine (SIE), which combines structured scoring, evidence analysis, public research, and AI-assisted interpretation across multiple startup dimensions.

> **Status:** Deployed and under active development.

**Live application:** https://app.venturegps.ai/

## What It Does

VentureGPS supports multiple startup intelligence workflows, including:

- Startup analysis
- Startup discovery and search
- Startup comparisons
- Rankings
- Founder workspaces
- Investor workflows
- Idea modeling and scenario exploration
- Pitch deck analysis and coaching
- Fundraising readiness
- Startup financial modeling
- Evidence and provenance tracking

The system accepts startup information from multiple sources, including structured user input, documents, websites, and public research.

## Startup Intelligence Engine

The Startup Intelligence Engine provides a structured framework for evaluating startup evidence.

The system analyzes six core pillars:

- Market
- Team
- Product
- Execution
- Traction
- Financial Health

Analysis is assembled into structured startup intelligence outputs using validated data models and an explicit scoring methodology.

Scoring methodology and implementation decisions are documented in the repository under:

`app/docs/`

## Evidence-Aware Analysis

A central design goal of VentureGPS is distinguishing between what is known, inferred, unavailable, or supplied through different evidence sources.

The analysis pipeline incorporates evidence validation and provenance rather than treating every model-generated statement as equally authoritative.

Scoring dimensions can distinguish among evidence categories such as:

- Public
- Inferred
- Private

The system validates model output against evidence requirements before incorporating it into structured analysis.

## Architecture

VentureGPS is split into separate backend and frontend applications:

```text
                 VentureGPS
                     │
          ┌──────────┴──────────┐
          │                     │
     Next.js Frontend      FastAPI Backend
          │                     │
          │                Analysis Pipeline
          │                     │
          │             ┌───────┴────────┐
          │             │                │
          │        AI Analysis      Public Research
          │             │                │
          │             └───────┬────────┘
          │                     │
          └──────────────► Structured Results
                                │
                           PostgreSQL
```

### Backend

The backend is built with Python and FastAPI.

Responsibilities include:

- Startup analysis workflows
- Evidence processing
- Startup scoring
- Public research enrichment
- PDF ingestion
- Website ingestion
- Authentication and authorization
- Persistence
- Reporting
- Observability
- Reliability and calibration tooling

### Frontend

The frontend is built with Next.js and TypeScript using the App Router.

It provides interfaces for:

- Startup profiles
- Founder workflows
- Investor workflows
- Idea Lab
- Startup comparisons
- Discovery
- Rankings
- Pitch deck coaching
- Fundraising scenarios
- Saved startups
- Evidence and intelligence exploration

Frontend API access is separated into typed API clients rather than embedding backend communication directly throughout UI components.

## Analysis Pipeline

A startup analysis follows a structured workflow.

```text
Input
  │
  ├── Text
  ├── PDF
  └── Website
       │
       ▼
Research Enrichment
       │
       ▼
Evidence Processing
       │
       ▼
Pillar Analysis
       │
       ▼
Validation
       │
       ▼
Deterministic Score Assembly
       │
       ▼
Structured Startup Intelligence
       │
       ▼
Persistence + User Interface
```

AI is used for appropriate probabilistic analysis and evidence interpretation.

Canonical scoring calculations are performed by application logic rather than allowing the language model to directly determine final weighted scores.

## Reliability and Evaluation

VentureGPS includes engineering infrastructure for evaluating and protecting the intelligence system.

The repository contains automated tests covering areas such as:

- Authentication
- Analysis workflows
- Concurrency
- Evidence validation
- Evidence provenance
- Public evidence consistency
- Scoring weights
- Scoring correctness
- Deterministic integration
- Security hardening
- Website URL security
- PDF ingestion
- Observability
- Financial calculations
- Founder workflows
- Investor workflows

The project also includes dedicated calibration and reliability tooling.

### Calibration

The calibration system evaluates scoring behavior against benchmark companies and expected ranges.

Calibration artifacts are kept separate from production scoring logic so benchmark outcomes can be used to identify systemic issues without simply tuning the system to individual examples.

### Reliability

Dedicated reliability tooling supports repeatable analysis and investigation of evidence separation, scoring behavior, and methodology changes.

## Security

The application includes controls around authenticated analysis workflows and external content ingestion.

Security-related implementation includes:

- Clerk-based authentication
- Backend token verification
- Authorized-party validation
- Fail-closed authentication configuration
- Administrative authorization
- Restricted CORS configuration
- Website URL security validation
- Environment-based secret management

Secrets and API credentials are excluded from source control.

## Tech Stack

### Backend

- Python
- FastAPI
- Pydantic
- PostgreSQL
- OpenAI
- Tavily

### Frontend

- TypeScript
- Next.js
- React
- Clerk

### Infrastructure

- Vercel
- Render
- PostgreSQL

## Testing

Backend tests are located under:

```text
app/tests/
```

Frontend tests are located under:

```text
dashboard/tests/
```

The repository also contains separate calibration and reliability harnesses for evaluating behavior beyond conventional application tests.

VentureGPS V2 (`app/v2/`) has its own `pytest`-based suite under `app/v2/tests/`, including static architecture-boundary enforcement. GitHub Actions (`.github/workflows/ci.yml`) runs this suite and the frontend's lint/typecheck/test/build checks on every push and pull request against `main` — see `docs/portfolio/CI.md` for how it isolates its disposable test database and how to reproduce every check locally.

## Documentation

Engineering and methodology documentation lives alongside the implementation.

Notable areas include:

```text
app/docs/
app/calibration/
app/reliability/
dashboard/docs/
DEPLOYMENT.md
```

These documents capture scoring methodology, evidence semantics, calibration work, reliability analysis, deployment procedures, and implementation decisions.

## Local Development

### Backend

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the API:

```bash
uvicorn app.api:app --reload --port 8000
```

The backend requires environment configuration for services such as PostgreSQL, OpenAI, Tavily, and authentication.

Secrets should be stored locally in environment files and must not be committed.

### Frontend

From the `dashboard/` directory:

```bash
npm install
npm run dev
```

The Next.js development server runs locally and communicates with the FastAPI backend through the configured API URL.

## Project Direction

VentureGPS is an ongoing engineering project focused on building trustworthy startup intelligence rather than treating AI output as inherently authoritative.

Development emphasizes:

- Explicit evidence provenance
- Structured and validated AI outputs
- Deterministic scoring behavior
- Reproducible evaluation
- Failure containment
- Security boundaries
- Documented methodology
- Clear separation between evidence, inference, and modeled assumptions

The goal is to use AI where probabilistic reasoning adds value while keeping authoritative calculations and system behavior under deterministic software control.
