# Chrono-Guard — Lunar Crew Health Companion

Frontend for the Chrono-Guard crew-health system: a space-themed dashboard for
tracking lunar-crew vitals, daily check-ins, mission scheduling, anomaly
detection against a personal baseline, fatigue assessment, and guidance
follow-ups.

## Stack

- **React + TypeScript** — pages, forms, dashboard, interactive components
- **Vite** — dev server and build tooling
- **Tailwind CSS v4** — responsive space theme styling
- **Dexie (IndexedDB)** — local-first storage so the app works offline
- **Recharts** — personal-baseline charts
- **lucide-react** — navigation icons

## Getting started

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # type-check + production build
npm run lint
```

> Demo data lives in your browser (IndexedDB). Use the scenario buttons on the
> dashboard ("Nominal week", "Sudden spike", "Sustained drift", "Bad sensor
> data") to seed 17 days of readings.

## Project structure

```
src/
  shared/types.ts        # domain types (measurements, detections, guidance…)
  data/                  # Dexie DB, validation, demo seed data
  anomaly/               # personal baseline (median/MAD) + anomaly detector
  pipeline.ts            # daily picture: series, detections, fatigue, guidance
  offline/syncQueue.ts   # local-first sync queue (drains when online)
  guidance/followup.ts   # guidance accept/skip/complete actions
  ui/                    # themed pages + reusable components (Panel, Chip…)
  App.tsx                # shell, navigation, tab routing
```

## Module ownership

- `src/ui/*`, `src/App.tsx`, `src/index.css` — Person 1 (frontend & visualization)
- `src/data/*`, `src/anomaly/*`, `src/pipeline.ts`, `src/offline/*`,
  `src/guidance/*` — logic modules implementing the agreed signatures; backend
  teammates can replace their internals without touching the UI.
