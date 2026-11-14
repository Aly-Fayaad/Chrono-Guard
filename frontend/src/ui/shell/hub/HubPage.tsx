import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles, Eye, Info } from "lucide-react";
import { useHealth } from "../../HealthContext";
import { usePrefs } from "../../prefs";
import { usePageTitle } from "../../usePageTitle";
import { useNow } from "../../hooks/useNow";
import { MOOD, type Mood } from "../mood";
import { Starfield } from "../Starfield";
import { CelestialBody } from "../CelestialBody";
import { MetClock } from "../../components/MetClock";
import { HUB_BODIES, bodyTeasers, type HubBodyDef } from "./hubBodies";

/** Absolute scene positions (desktop) — a loose orbital arrangement. */
const LAYOUT: Record<string, { left: string; top: string; size: number; floatDelay: string }> = {
  today:     { left: "30%",  top: "46%", size: 150, floatDelay: "0s" },
  checkin:   { left: "58%",  top: "58%", size: 104, floatDelay: "1.2s" },
  schedule:  { left: "74%",  top: "26%", size: 132, floatDelay: "2.1s" },
  guidance:  { left: "12%",  top: "20%", size: 92,  floatDelay: "3.0s" },
  restore:   { left: "45%",  top: "12%", size: 108, floatDelay: "1.7s" },
  earthlink: { left: "18%",  top: "68%", size: 88,  floatDelay: "2.6s" },
};

/** Vertical layout (mobile / small screens). */
const LAYOUT_STACK: Record<string, { size: number }> = {
  today: { size: 116 },
  checkin: { size: 92 },
  schedule: { size: 104 },
  guidance: { size: 80 },
  restore: { size: 88 },
  earthlink: { size: 76 },
};

/**
 * The Hub — "Observation Deck".
 * A full-viewport space scene: Earthrise horizon, parallax starfield whose
 * mood follows crew status, and six celestial bodies (one per destination).
 * Keyboard: Tab/Arrows travel between bodies, Enter opens, Esc returns.
 * "Simple navigation" swaps the scene for a plain list.
 */
export function HubPage() {
  usePageTitle("Observation Deck");
  const health = useHealth();
  const { prefs, setPref } = usePrefs();
  const navigate = useNavigate();
  const now = useNow(30_000);

  const mood = health.data ? MOOD[health.data.assessment.status] : MOOD.insufficient_data;
  const teasers = useMemo(() => bodyTeasers(health, now), [health, now]);

  const [flying, setFlying] = useState<{ x: number; y: number; label: string } | null>(null);
  const bodyRefs = useRef<Record<string, HTMLAnchorElement | null>>({});

  // Preload the hero so first paint shows the horizon immediately.
  useEffect(() => {
    const img = new Image();
    img.src = "/assets/space/hub-earthrise.jpg";
  }, []);

  function openBody(b: HubBodyDef, el: HTMLElement | null) {
    if (prefs.reduceEffects) {
      navigate(b.path);
      return;
    }
    const rect = el?.getBoundingClientRect();
    setFlying({
      x: rect ? rect.left + rect.width / 2 : window.innerWidth / 2,
      y: rect ? rect.top + rect.height / 2 : window.innerHeight / 2,
      label: b.breadcrumb,
    });
    window.setTimeout(() => {
      navigate(b.path);
      window.setTimeout(() => setFlying(null), 120);
    }, 700);
  }

  // Roving arrow-key navigation across the bodies.
  function onKeyDown(e: React.KeyboardEvent, index: number) {
    const keys = ["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"];
    if (!keys.includes(e.key)) return;
    e.preventDefault();
    const dir = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : -1;
    const next = (index + dir + HUB_BODIES.length) % HUB_BODIES.length;
    bodyRefs.current[HUB_BODIES[next].key]?.focus();
  }

  const sceneHidden = Boolean(flying);

  return (
    <div className={`relative flex min-h-screen flex-col overflow-hidden`}>
      {/* ---- Backdrop ---- */}
      <div aria-hidden className="pointer-events-none absolute inset-0 z-0">
        <Starfield
          density={mood.starDensity}
          auroraColor={mood.auroraColor}
          auroraAlpha={mood.auroraAlpha}
          staticOnly={prefs.reduceEffects}
        />
        {/* status veil — very low alpha wash, transitions gently */}
        <div
          className="absolute inset-0 transition-[background] duration-1000"
          style={{ background: mood.veil }}
        />
        {/* Earthrise / lunar horizon photo at the bottom (scrimmed) */}
        <div className="absolute inset-x-0 bottom-0 h-[42vh]">
          <img
            src="/assets/space/hub-earthrise.jpg"
            alt=""
            fetchPriority="high"
            className={`hub-drift h-full w-full object-cover object-bottom opacity-90 ${
              prefs.reduceEffects ? "" : ""
            }`}
            style={{ filter: prefs.reduceEffects ? "none" : "saturate(0.92)" }}
            onError={(e) => (e.currentTarget.style.display = "none")}
          />
          <div className="scrim absolute inset-0" />
        </div>
        {/* top vignette for header legibility */}
        <div className="absolute inset-x-0 top-0 h-28 bg-gradient-to-b from-void/85 to-transparent" />
      </div>

      {/* ---- Header ---- */}
      <header className="relative z-20 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-3 py-3 sm:px-6">
        <div className="flex items-center gap-2.5">
          <span
            className="flex h-9 w-9 items-center justify-center rounded-full border border-earth/40 bg-deep/80 font-mono text-[11px] text-earth"
            aria-hidden
          >
            CG
          </span>
          <div>
            <p className="font-display text-[14px] font-medium text-moonlight">Observation Deck</p>
            <p className="font-mono text-[10px] tracking-[0.18em] text-regolith">CHRONOGUARD · LUN-4</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <MetClock />
          <button
            type="button"
            onClick={() => setPref("reduceEffects", !prefs.reduceEffects)}
            aria-pressed={prefs.reduceEffects}
            aria-label="Reduce effects: turn off animation and heavy imagery"
            className={`motion-fade inline-flex min-h-[44px] items-center gap-1.5 rounded-full border px-3 text-[11px] ${
              prefs.reduceEffects
                ? "border-aurora/50 bg-aurora/10 text-aurora"
                : "border-hairline text-regolith hover:text-moonlight"
            }`}
          >
            <Sparkles size={13} aria-hidden />
            <span className="hidden sm:inline">Reduce effects</span>
          </button>
          <button
            type="button"
            onClick={() => setPref("simpleNav", !prefs.simpleNav)}
            aria-pressed={prefs.simpleNav}
            aria-label="Simple navigation: swap the scene for a plain list of destinations"
            className={`motion-fade inline-flex min-h-[44px] items-center gap-1.5 rounded-full border px-3 text-[11px] ${
              prefs.simpleNav
                ? "border-aurora/50 bg-aurora/10 text-aurora"
                : "border-hairline text-regolith hover:text-moonlight"
            }`}
          >
            <Eye size={13} aria-hidden />
            <span className="hidden sm:inline">Simple navigation</span>
          </button>
        </div>
      </header>

      {/* ---- Status line (text + icon, never color alone) ---- */}
      <div className="relative z-20 px-3 sm:px-6">
        <p className="glass-soft mx-auto flex max-w-fit flex-wrap items-center gap-2 rounded-full border border-hairline px-4 py-2 text-[12px]">
          <span
            aria-hidden
            className="h-2 w-2 rounded-full ring-1 ring-current/40"
            style={{ backgroundColor: mood.accent }}
          />
          <span className="font-medium" style={{ color: mood.accent }}>{mood.label}</span>
          <span className="text-regolith">·</span>
          <span className="text-moonlight/90">{mood.hint}</span>
        </p>
      </div>

      {/* ---- Scene ---- */}
      {prefs.simpleNav ? (
        <SimpleNav mood={mood} teasers={teasers} onOpen={openBody} />
      ) : (
        <main
          aria-label="Destinations as celestial bodies"
          className={`relative z-10 mx-auto w-full max-w-[1400px] flex-1 px-4 ${
            sceneHidden ? "opacity-0 transition-opacity duration-500" : "opacity-100 transition-opacity duration-700"
          }`}
        >
          {/* Desktop: orbital arrangement */}
          <ul className="absolute inset-0 hidden md:block" role="list">
            {HUB_BODIES.map((b, i) => {
              const pos = LAYOUT[b.key];
              return (
                <li
                  key={b.key}
                  className="absolute"
                  style={{ left: pos.left, top: pos.top, transform: "translate(-50%, -50%)" }}
                >
                  <div className={prefs.reduceEffects ? "" : "body-float"} style={{ animationDelay: pos.floatDelay }}>
                    <a
                      ref={(el) => { bodyRefs.current[b.key] = el; }}
                      href={`#${b.path}`}
                      onClick={(e) => {
                        e.preventDefault();
                        openBody(b, e.currentTarget);
                      }}
                      onKeyDown={(e) => onKeyDown(e, i)}
                      className="motion-fade group block rounded-full outline-offset-8 hover:scale-[1.04] focus-visible:scale-[1.04]"
                    >
                      <span className="sr-only">{b.name} — </span>
                      <CelestialBody
                        kind={b.kind}
                        size={pos.size}
                        statusColor={b.key === "today" ? mood.accent : undefined}
                        rings={b.kind === "sun"}
                        label={<span className={`group-hover:text-moonlight ${b.accentCls}`}>{b.breadcrumb}</span>}
                        teaser={teasers[b.key]}
                      />
                    </a>
                  </div>
                </li>
              );
            })}
          </ul>

          {/* Mobile / tablet: vertical orbit stack */}
          <ul className="flex flex-col items-center gap-5 pb-10 pt-6 md:hidden" role="list">
            {HUB_BODIES.map((b, i) => (
              <li key={b.key} className="w-full max-w-sm">
                <a
                  href={`#${b.path}`}
                  onClick={(e) => {
                    e.preventDefault();
                    openBody(b, e.currentTarget);
                  }}
                  onKeyDown={(e) => onKeyDown(e, i)}
                  className="glass motion-fade flex min-h-[76px] w-full items-center gap-4 rounded-panel px-4 py-3 active:scale-[0.98]"
                >
                  <CelestialBody
                    kind={b.kind}
                    size={LAYOUT_STACK[b.key].size}
                    statusColor={b.key === "today" ? mood.accent : undefined}
                    rings={b.kind === "sun"}
                  />
                  <span className="min-w-0">
                    <span className={`font-display block text-[15px] font-medium ${b.accentCls}`}>{b.breadcrumb}</span>
                    <span className="tnum mt-0.5 block truncate text-[11px] text-regolith">{teasers[b.key]}</span>
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </main>
      )}

      {/* ---- Footer hints ---- */}
      <footer className="relative z-20 px-3 pb-5 sm:px-6">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-2">
          <p className="flex items-center gap-1.5 text-[11px] text-ink">
            <Info size={12} aria-hidden />
            Potential concern for human review. Not a diagnosis.
          </p>
          <p className="tnum hidden text-[11px] text-ink sm:block">
            Tab / arrows to travel · Enter to open · Esc returns
          </p>
          <p className="text-[11px] text-ink">
            Imagery courtesy of NASA. ChronoGuard is not affiliated with or endorsed by NASA.{" "}
            <a href="#/credits" className="underline decoration-ink/50 underline-offset-2 hover:text-regolith">Image credits</a>
          </p>
        </div>
      </footer>

      {/* ---- Fly-to overlay ---- */}
      {flying && (
        <div aria-hidden className="pointer-events-none fixed inset-0 z-50 overflow-hidden">
          <div
            className="absolute rounded-full bg-void"
            style={{
              left: flying.x,
              top: flying.y,
              width: "320vmax",
              height: "320vmax",
              marginLeft: "-160vmax",
              marginTop: "-160vmax",
              animation: "fly-circle 700ms cubic-bezier(0.4, 0, 0.2, 1) forwards",
            }}
          />
          <p
            className="font-display absolute inset-x-0 top-1/2 -translate-y-1/2 text-center text-[18px] text-moonlight/90"
            style={{ animation: "hub-fade-in 400ms ease-out 250ms both" }}
          >
            Traveling to {flying.label}…
          </p>
        </div>
      )}
    </div>
  );
}

/** Plain-list alternative to the scene (Simple navigation). */
function SimpleNav({
  mood,
  teasers,
  onOpen,
}: {
  mood: Mood;
  teasers: Record<string, string>;
  onOpen: (b: HubBodyDef, el: HTMLElement | null) => void;
}) {
  return (
    <main className="relative z-10 mx-auto w-full max-w-xl flex-1 px-4 pb-10">
      <ul className="flex flex-col gap-3">
        {HUB_BODIES.map((b) => (
          <li key={b.key}>
            <a
              href={`#${b.path}`}
              onClick={(e) => {
                e.preventDefault();
                onOpen(b, e.currentTarget);
              }}
              className="glass motion-fade flex min-h-[64px] items-center justify-between gap-3 rounded-panel px-4 py-3 hover:border-earth/40"
            >
              <span>
                <span className={`font-display block text-[14px] font-medium ${b.accentCls}`}>
                  {b.name} — {b.breadcrumb}
                </span>
                <span id={`hub-s-ts-${b.key}`} className="tnum mt-0.5 block text-[11px] text-regolith">{teasers[b.key]}</span>
              </span>
              <span aria-hidden className="text-regolith">›</span>
            </a>
          </li>
        ))}
      </ul>
      <p className="mt-4 flex items-center gap-2 text-[11px] text-ink">
        <span aria-hidden className="h-2 w-2 rounded-full" style={{ backgroundColor: mood.accent }} />
        <span>Current status: <span className="font-medium" style={{ color: mood.accent }}>{mood.label}</span></span>
      </p>
    </main>
  );
}
