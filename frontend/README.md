# ChronoGuard — Cosmos Hub

A space-themed, healing "Cosmos Hub" redesign of the ChronoGuard crew-health
console for long lunar missions. Emotional target: **awe + calm + orientation** —
the Overview Effect, not an admin panel.

## Run it

Start the backend first (see `backend/README.md`), then:

```bash
npm install
cp .env.example .env.local   # optional; defaults to http://127.0.0.1:8000/api/v1
npm run dev      # → http://localhost:5173 (or the next free port)
```

The console reads everything health-related from `GET /api/v1/crew/{id}/overview`
and writes check-ins/tasks to the API. If the API is unreachable, writes are kept
in the Dexie queue and retried automatically.

Demo/mock scenarios (append before the hash, e.g. `http://localhost:5174/?mock=sudden#/`):

| Query | Scenario |
|---|---|
| `?mock=normal` | everything within personal range |
| `?mock=sudden` | sudden anomaly (heart rate + HRV) → **Monitor** mood |
| `?mock=sustained` | sustained drift across metrics → **Review suggested** |
| `?mock=data-quality` | sensor-quality warnings → **Insufficient data** |

Production build: `npm run build` (type-checks with `tsc -b`, bundles with Vite).

## The Hub (`#/`)

The landing page is the **Observation Deck**: a full-viewport space scene with a
parallax starfield (canvas, 3 layers, ~30 fps, paused when the tab is hidden), a
procedural aurora whose color/intensity follows the crew's status, and a real
NASA **Earthset over the lunar horizon** (Artemis II) at the bottom. Six
destinations are celestial bodies:

| Body | Destination | Live teaser |
|---|---|---|
| 🜨 Earth (status ring) | `#/today` — dashboard | "Status: Monitor · Index 52 · 2 unusual" |
| ☾ Moon | `#/check-in` — ritual | "Last check-in 6 h ago" |
| ☀ Sun + orbit rings | `#/schedule` — circadian | "Next: EVA rock sampling · T−02:14" |
| ✦ Constellation | `#/guidance` | "3 suggestions waiting" |
| ☁ Aurora | `#/restore` — breathing | "Guided breathing · 4-6 rhythm" |
| 🛰 Relay satellite | `#/earth` — Earth view | "Comms relay · view Earth" |

Click/Enter = **fly-to** transition (700 ms expanding circle + fade). Every inner
page has a mini-orbit nav, breadcrumb ("Hub › Earth › Today"), Esc-to-return,
MET clock, offline pill, and the same glass language.

## Accessibility

- Full keyboard support: Tab/arrow keys travel between bodies, Enter opens, Esc
  returns. Visible focus rings everywhere.
- **Simple navigation** toggle (persisted): swaps the scene for a plain list.
- **Reduce effects** toggle (persisted): stops animation, blur and imagery.
  `prefers-reduced-motion` is honored automatically.
- Status is never color alone — icon + LED + text always accompany it.
- Lighthouse: 100 accessibility / 100 best-practices / 100 SEO.

## Data layer

The backend is the single source of truth. `src/api/client.ts` calls the FastAPI
routes; `src/api/overview.ts` maps the response into the existing view model.
Mission epoch/day length, MET, D+ labels, personal-baseline detections, fatigue
status and assessment text all come from the server. `src/ui/lib/time.ts` only
formats the values the backend returns (the built-in epoch/24.65 fallback exists
solely to avoid an empty clock on the first paint before the overview response
arrives). Schedule labels use the operational 24.65 h mission day, while the
circadian light arcs stay on the published 24 h Earth clock. Dexie is still used
for guidance follow-ups and the offline write queue. The `?mock=` fixture layer is
unchanged for design work (mock writes are intentionally no-ops).

## Imagery

Self-hosted NASA photography in `public/assets/space/` (no hotlinking; works
offline). See **ASSET_CREDITS.md** and the in-app `#/credits` page. All bodies,
starfields, gauges, moon phases and constellations are procedural SVG/Canvas
fallbacks — the Hub looks right even with every photo removed. No NASA insignia
is used; footer carries the required non-endorsement line.

## Structure

```
src/ui/
  shell/            Starfield, CelestialBody, MiniOrbitNav, PageShell, mood map
  shell/hub/        HubPage, hubBodies (live teasers)
  pages/            Today, Check-in (ritual), Schedule (+circadian arcs),
                    Guidance (+constellation), Restore (breathing), EarthView, Credits
  components/       Panels, gauges, charts, badges (reused + re-themed)
  hooks/, lib/      useHealthData (mock-aware), time/format helpers
  mock/             ?mock= fixtures (normal | sudden | sustained | data-quality)
```
