# ChronoGuard — Lunar Crew Health Console

Offline-capable crew-health console for lunar missions: personal-baseline
anomaly monitoring, fatigue assessment, daily check-ins, mission scheduling
and guidance follow-ups. Designed as a calm, precise mission-operations
console — data-first, never gimmicky.

## Stack

- **React + TypeScript (strict)** — pages, forms, dashboard, interactive components
- **Vite** — dev server and build tooling
- **Tailwind CSS v4** — all design tokens live in the `@theme` block of `src/index.css`
- **Recharts** — personal-baseline charts
- **React Router** — Today / Check-in / Schedule / Guidance
- **lucide-react** — status and navigation icons
- **@fontsource IBM Plex Sans/Mono** — self-hosted fonts, fully offline
- **Dexie (IndexedDB)** — local-first storage behind the sync queue

No CDN fonts, remote images or external scripts: the app renders fully with
the network off.

## Getting started

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # strict type-check + production build
npm run lint
```

## Demo scenarios

Static fixtures with the identical pipeline shape are available behind a URL
parameter (no data layer needed):

```
http://localhost:5173/?mock=normal
http://localhost:5173/?mock=sudden
http://localhost:5173/?mock=sustained
http://localhost:5173/?mock=data-quality
```

Without the parameter the app consumes the real pipeline (`src/pipeline.ts`)
via the `useHealth` hook. Real mode with an empty database offers a
"Load demo data" button that seeds IndexedDB.

## Status language

The UI never uses color alone: every status pairs an icon, a text label and a
color. Fixed, careful phrasing: "Within personal range", "Unusual for
baseline", "Not enough history", "Data-quality warning", "Potential concern,
review suggested". Data-quality states are slate with a diagonal hatch so a
sensor problem never reads as a health alarm. Every assessment carries the
footnote: "Potential concern for human review. Not a diagnosis."

## Project structure

```
src/
  shared/types.ts        # domain types (owned by data/pipeline team)
  data/                  # Dexie DB, validation, demo seed
  anomaly/               # personal baseline (median/MAD) + detector
  pipeline.ts            # daily picture: series, detections, fatigue, guidance
  offline/syncQueue.ts   # local-first sync queue
  guidance/followup.ts   # guidance accept/skip/complete
  ui/
    AppShell.tsx         # rail (md+), top bar (MET clock, connectivity), mobile tab bar
    config.ts            # crew id, mission epoch, metric metadata
    lib/                 # time (MET formatting), number formatting
    hooks/               # useHealthData (integration seam), useMetClock, useNow
    mock/                # scenario fixtures + mock data source
    components/          # Panel, StatusBadge, MetricTile, ArcGauge, charts…
    pages/               # Today, CheckIn, Schedule, Guidance
```

`src/ui` owns all presentation. It consumes shared types and the pipeline
outputs only — no detection or assessment logic lives in the UI.

## Layout

- **≥1024px** — expanded 220px left rail
- **768–1023px** — 72px icon rail
- **<768px** — bottom tab bar (44px+ touch targets, safe-area padding)
- Max content width 1200px; panels reflow 4 → 2 → 1 columns.
