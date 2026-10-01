# VentureGPS — Frontend

Next.js 16 (App Router) frontend for VentureGPS. See the repository root [`README.md`](../README.md) for
the full project overview, architecture, and backend setup — this file covers only what's specific to this
directory.

## Setup

```bash
npm install
npm run dev   # http://localhost:3000
```

Requires the backend running separately (`uvicorn app.api:app --reload --port 8000` from the repo root) and
expects it at `NEXT_PUBLIC_API_URL` (defaults to `http://127.0.0.1:8000` if unset). For Clerk authentication
in local development, see the root README's "Developer setup" and `DEPLOYMENT.md`'s "Local development
(Clerk)" section — a keyless, no-account-needed mode is available for `npm run dev` (not for a production
build).

## Tests

```bash
npm test             # all suites (35 suites, 434 tests)
npx tsc --noEmit
npm run lint
npm run build
```

This Next.js version has conventions that may differ from training-data knowledge for any AI coding
assistant working in this directory — see `AGENTS.md`.
