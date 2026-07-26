# Construction Intel -- Frontend

Next.js 14 (App Router) + TypeScript + Tailwind CSS frontend for the Construction
Intel permit/property search product. See the root [`../README.md`](../README.md)
for the overall product/architecture, and [`BLOCKERS.md`](./BLOCKERS.md) in this
directory for what's real vs. stubbed and what needs a human decision.

## Status

**This has been built, installed, and built successfully with a real Node.js
toolchain** (Node v24.18.0 / npm 11.16.0) as of this writing:

- `npm install` -- succeeds, produces a real `package-lock.json`.
- `npm run build` -- succeeds (`next build`, static + one dynamic route, all
  pages compile and type-check).
- `npm run lint` -- clean, no errors or warnings.
- `npm run dev` -- boots in ~1.3s; `/`, `/search`, `/permits/[id]`, and
  `/dashboard` were all fetched and returned 200 with no server errors.

## Stack

- **Next.js 14** (App Router) + **TypeScript** + **Tailwind CSS**
- **shadcn/ui**-style components (Radix primitives + `class-variance-authority`,
  hand-added under `components/ui/` -- not pulled via the `shadcn` CLI since
  that requires network access to a component registry at generation time;
  the resulting components are the same code the CLI would have scaffolded)
- **TanStack Query v5** for all data fetching (loading/error states throughout)
- **MapLibre GL JS** for the map view (NOT Mapbox -- see [BLOCKERS.md](./BLOCKERS.md)
  for exactly which free tile source is used and its caveats)
- **Recharts** for the analytics dashboard
- **next-themes** for the dark mode toggle

## Setup

```bash
cd frontend
npm install
cp .env.local.example .env.local   # optional -- defaults work with no backend running
npm run dev
```

Then open http://localhost:3000. The app works immediately with **no backend
running** -- every API call in `lib/api.ts` automatically falls back to the
local fixtures in `lib/fixtures.ts` if the backend at `NEXT_PUBLIC_API_URL`
(default `http://localhost:8000`) isn't reachable. To use live data, start the
backend (see `../backend/README` / root README) and just reload -- no frontend
config changes needed.

Set `NEXT_PUBLIC_USE_MOCKS=true` in `.env.local` to force fixture data even if
a backend happens to be running (useful when working on the UI in isolation).

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Start the dev server at http://localhost:3000 |
| `npm run build` | Production build (also type-checks and lints) |
| `npm run start` | Serve the production build (`npm run build` first) |
| `npm run lint` | ESLint (`next lint`) |
| `npm run typecheck` | `tsc --noEmit` only |

## Directory layout

```
frontend/
  app/                    Routes (App Router) -- one folder per page
    page.tsx              Landing page
    search/                /search -- filter sidebar + list/map results
    permits/[id]/          /permits/:id -- detail, history, scores
    dashboard/             /dashboard -- analytics
    login/, signup/        Auth UI stubs
    saved-searches/        Saved searches UI (localStorage-backed stub)
    alerts/                Alert subscriptions UI (localStorage-backed stub)
    layout.tsx             Root layout: navbar, footer, providers
    providers.tsx           TanStack Query + next-themes providers
  components/
    ui/                    shadcn/ui-style primitives (Button, Card, Table, ...)
    layout/                Navbar, footer, theme toggle
    search/                Filter sidebar, results table/map, pagination
    permits/                Detail tabs, version timeline, score explanations
    dashboard/              Charts (Recharts) + stat tiles
    saved-searches/, alerts/, auth/   Feature-specific UI
  lib/
    api.ts                 Typed API client -- real fetch + automatic mock fallback
    types.ts                Types mirroring backend/app/schemas.py exactly
    fixtures.ts             Local sample data (20 permits, 4 jurisdictions)
    scoring.ts               TS port of the backend's scoring engine (fixtures only)
    local-store.ts          localStorage persistence for saved searches/alerts/auth stubs
    chart-colors.ts          Dataviz-skill-validated categorical/sequential palette
    hooks/                   TanStack Query hooks (usePermitsSearch, usePermit, ...)
```

## Backend contract

`lib/api.ts` targets:

- `GET /permits` -- search/filter (see `PermitSearchParams` in `lib/types.ts`)
- `GET /permits/{id}`
- `GET /properties/{id}`
- `GET /export` -- CSV download
- `GET /jurisdictions`

all under `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). This matches
`backend/app/main.py` / `backend/app/routers/*` as implemented today. The
filter sidebar also sends `city`, `county`, `zip`, `radius_miles`, `builder`,
`architect`, `owner_occupied`, and `property_type` -- fields the product spec
calls for that the backend doesn't filter on yet (see BLOCKERS.md). FastAPI
ignores undeclared query params rather than erroring, so this is
forward-compatible and requires no frontend change once the backend adds them.

`saved-searches`, `alerts`, and `auth` endpoints are called optimistically too,
so those features switch from the localStorage stub to real persistence
automatically the moment the backend implements them -- see BLOCKERS.md.
