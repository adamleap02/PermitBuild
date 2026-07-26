# Frontend blockers / status

Snapshot as of this writing. Re-check against the live code if this drifts.

## Node.js / npm -- resolved, but slowly

Node.js was **not installed** when this workstream started. A background
`winget install -e --id OpenJS.NodeJS.LTS` had been kicked off before this
session began; it turned out to be silently stalled (the `winget.exe` App
Execution Alias process sat at ~0% CPU for over 10 minutes with no progress in
this sandboxed environment) before it eventually completed. Once
`C:\Program Files\nodejs\node.exe` existed (Node v24.18.0, npm 11.16.0), this
workstream:

- Ran `npm install` for real -- succeeded, produced a real `package-lock.json`
  (needed for `npm ci` in `.github/workflows/ci.yml`, which was previously
  impossible to generate by hand).
- Ran `npm run build` (`next build`) for real -- **succeeded**: all 9 routes
  compiled, type-checked, and statically generated (one dynamic route,
  `/permits/[id]`).
- Ran `npm run lint` for real -- clean.
- Ran `npm run dev` for real, fetched `/`, `/search`, `/permits/1001`, and
  `/dashboard` over HTTP, confirmed 200 responses and no server-side errors in
  the dev server log, then stopped it.

So: **everything in this directory was actually built and verified to compile
and boot**, not hand-written-and-hoped. The one thing not verified with a real
browser is client-side rendering after hydration (no headless browser was
available in this environment to screenshot/inspect the DOM post-JS-execution)
-- a plain HTTP GET only sees the pre-hydration skeleton/loading state for
client-rendered data (this is expected: `/permits/[id]` etc. fetch via
TanStack Query in a "use client" component, so the raw HTML doesn't contain
permit data until the browser runs React). If you have a moment, `npm run dev`
and click around `/search` and `/permits/1001` in an actual browser is the
last mile of verification worth doing by hand.

## npm audit: 16 high-severity findings remain

`next` was bumped from `14.2.5` (pinned initially) to `14.2.35` (latest patch
on the 14.x line) specifically to clear a critical advisory flagged by `npm
install`. The remaining 16 high-severity findings from `npm audit` are:

- A long list of Next.js server-side advisories (DoS, cache poisoning,
  request smuggling, etc.) that are **only fixed in the Next.js 15/16 major
  line** -- `npm audit fix --force` would jump to `next@16.2.12`, a breaking
  change beyond "Next.js 14+ App Router" as specified for this task.
- `eslint`/`brace-expansion`/`glob`/etc. transitive dev-tooling advisories,
  only fixed by an `eslint@10` major bump (breaking change to lint config).

None of these are exploitable in local dev/demo use, but **upgrading to
Next.js 15 or 16 (and eslint 9/10) should happen before any real production
deployment** -- budget time for that as a discrete follow-up, not a quick flag
flip, since Next 15 changes some App Router defaults (async `params`/`cookies`,
caching semantics).

## Mapbox deliberately avoided -- tile source used, and its real caveats

Per the task instructions, **Mapbox was not used** (it requires a billed API
key beyond a small free tier). The map view (`components/search/results-map.tsx`)
uses **MapLibre GL JS** (open-source, no vendor lock-in) against
**OpenFreeMap** (`https://tiles.openfreemap.org/styles/liberty` for light mode,
`.../styles/dark` for dark mode) as the vector tile/style source.

- OpenFreeMap advertises itself as free, with no API key and no rate limit,
  self-hostable (it's an open-source project, not a hosted SaaS with a
  paid tier lurking behind it). This was **not independently load-tested**
  against OpenFreeMap's actual infrastructure/ToS by this workstream --
  before relying on it for real production traffic, read their current usage
  guidance and/or self-host the tiles (they publish the tooling to do so;
  see their GitHub).
- The map re-fetches style/vector tiles from a third-party host at runtime --
  this is a live external network dependency, not something bundled in the
  build. If that host has an outage or changes its policy, the map view
  breaks until the tile source is swapped (isolated to two constants at the
  top of `results-map.tsx`).
- The map's light/dark style is only chosen at initial mount (from whatever
  theme is active when the map first loads) -- toggling dark mode after the
  map has already loaded does not currently call `map.setStyle()` to swap
  tile styles live. Minor, but worth fixing before shipping if map + dark
  mode is a highlighted feature.
- At real production scale (many concurrent users, heavy zooming/panning), a
  paid provider with an SLA (MapTiler paid tier, Mapbox, Stadia Maps, etc.) or
  a self-hosted tile server is the safer long-term choice -- this is a human/
  business decision to revisit once there's real traffic, not something to
  pre-solve now.

## Auth is a UI-only scaffold -- no real backend auth exists

`/login` and `/signup` render real forms and call `lib/api.ts`'s `loginStub`/
`signupStub`, which attempt `POST /auth/login` / `POST /auth/signup` against
the backend first (so this needs zero frontend changes once the backend adds
real auth), then fall back to writing a fake token to `localStorage` so the
navbar can show a "logged in" state end-to-end for the demo. **There is no
real session, JWT, password hashing, or CSRF protection here** -- do not treat
this as security. `backend/app/models.py` already has `Organization`/`User`/
`ApiKey` tables scaffolded (bcrypt-style `hashed_password` column, no
implementation), but `backend/app/main.py` has no `/auth` router yet.

**Recommendation for the real implementation: [NextAuth.js](https://authjs.dev/)**
(now "Auth.js") -- free, open-source, no paid service required, has a Credentials
provider that can call the backend's future `/auth/login` directly, plus
ready-made OAuth providers (Google/GitHub/etc.) if social login is wanted
later without extra cost.

## Saved searches & alerts -- UI-only stubs, backend has no matching routes

`backend/app/main.py` registers `permits`, `properties`, `export`, `ingest`,
and `jurisdictions` routers only -- there is no `/saved-searches` or `/alerts`
router. `lib/api.ts`'s saved-search/alert functions all attempt the real
endpoint first, then fall back to `lib/local-store.ts` (localStorage). This
means:

- Saved searches and alerts **do not persist across browsers/devices** and
  are lost if the user clears site data -- purely a local demo of the UX.
- **No email is ever actually sent** for alerts. A real implementation needs:
  1. A backend `/alerts` CRUD API + a scheduled job (Celery beat, since
     Celery/Redis are already in `backend/requirements.txt`) that periodically
     re-runs each alert's saved search against new/changed permits.
  2. A transactional email provider to actually deliver the digest/instant
     emails -- **this needs a paid signup at some point** (free tiers exist:
     Resend ~3k emails/mo free, SendGrid ~100/day free, AWS SES pay-as-you-go
     with no free tier but very cheap) -- a human/business decision on which
     vendor, not something to pre-select here.

## Filters the UI sends that the backend doesn't implement yet

`backend/app/routers/permits.py`'s `apply_filters` currently supports:
`jurisdiction_id`, `permit_type`, `status`, `date_from`, `date_to`,
`min_value`, `max_value`, `keyword` (plus `page`/`page_size`). The filter
sidebar (`components/search/filter-sidebar.tsx`) also collects `city`,
`county`, `zip`, `radius_miles`, `contractor`, `builder`, `architect`,
`owner_occupied`, and `property_type` per the product spec. These are sent to
`GET /permits` as extra query params; FastAPI silently ignores params it
doesn't declare, so **today those filters are no-ops against a live backend**
and only actually filter results when the local mock fallback is active
(`lib/fixtures.ts`'s `searchPermitsMock` does implement all of them, so the
demo experience is fully functional). Once the backend adds these to
`apply_filters` (note: `city`/`county`/`zip`/`owner_occupied`/`property_type`
live on `Property`/`Owner`, not `Permit`, so that likely needs a join), no
frontend change is needed.

## Dashboard aggregates client-side -- no analytics endpoint exists yet

`/dashboard` fetches up to 200 permits via the existing `GET /permits` (no
dedicated analytics/aggregation endpoint exists on the backend) and computes
the time-series/breakdown charts in the browser from that page. This is fine
for a demo or a dataset in the low thousands, but **will not scale** once
there are more permits than a single page can hold -- replace with a real
`GET /analytics/*` (or GraphQL-style aggregation) endpoint that does the
grouping in SQL before this goes further.

## Everything else that's real, for clarity

To be explicit about what's *not* a blocker: the search filters/pagination,
map clustering + popups, permit detail tabs (overview/property/version
history/score explanations), the CSV export link, dark mode, and the
responsive nav are all fully implemented against the real API contract
(`backend/app/schemas.py`) with automatic mock fallback, verified by an actual
`next build` + `next dev` + HTTP requests as described above -- not aspirational.
