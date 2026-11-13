import { useEffect, useRef, useState } from "react";
import { Pause, Play, Volume2, VolumeX } from "lucide-react";
import { usePrefs } from "../prefs";
import { usePageTitle } from "../usePageTitle";
import { PageShell } from "../shell/PageShell";
import { SmartImage } from "../components/SmartImage";

/**
 * Restore — the Aurora body's calm mode.
 * A guided 4-6 breathing exercise: a small moon-like body expands on the
 * orbit ring as you inhale (4 s) and contracts as you exhale (6 s).
 * Reduced motion / reduce-effects → static ring + text countdown.
 * Optional soft ambient audio (off by default, user-gesture started).
 */
const PHASE_IN = 4;
const PHASE_OUT = 6;

export function RestorePage() {
  usePageTitle("Restore");
  const { prefs } = usePrefs();
  const calm = prefs.reduceEffects;

  const [running, setRunning] = useState(true);
  const [phase, setPhase] = useState<"in" | "out">("in");
  const [phaseLeft, setPhaseLeft] = useState(PHASE_IN);
  const [audioOn, setAudioOn] = useState(false);
  const audioRef = useRef<{ ctx: AudioContext; stop: () => void } | null>(null);

  // Breathing timer (1 s ticks; static countdown when reduced).
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => {
      setPhaseLeft((left) => {
        if (left > 1) return left - 1;
        setPhase((p) => {
          const nextP = p === "in" ? "out" : "in";
          setPhaseLeft(nextP === "in" ? PHASE_IN : PHASE_OUT);
          return nextP;
        });
        return 1;
      });
    }, 1000);
    return () => window.clearInterval(id);
  }, [running]);

  // Optional ambient drone: two low sine oscillators + slow tremolo.
  useEffect(() => {
    if (!audioOn) return;
    const AudioCtor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtor) return;
    const ctx = new AudioCtor();
    const master = ctx.createGain();
    master.gain.value = 0;
    master.connect(ctx.destination);

    const oscs = [110, 164.8].map((f) => {
      const o = ctx.createOscillator();
      o.type = "sine";
      o.frequency.value = f;
      const g = ctx.createGain();
      g.gain.value = 0.06;
      o.connect(g).connect(master);
      o.start();
      return o;
    });

    // slow breathing tremolo (10 s cycle — matches the 4-6 breath)
    const lfo = ctx.createOscillator();
    lfo.frequency.value = 0.1;
    const lfoGain = ctx.createGain();
    lfoGain.gain.value = 0.03;
    lfo.connect(lfoGain).connect(master.gain);
    lfo.start();

    master.gain.linearRampToValueAtTime(0.05, ctx.currentTime + 2);

    audioRef.current = {
      ctx,
      stop: () => {
        try {
          master.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.5);
          window.setTimeout(() => void ctx.close(), 600);
        } catch { /* already closed */ }
      },
    };
    return () => {
      audioRef.current?.stop();
      audioRef.current = null;
      void oscs;
    };
  }, [audioOn]);

  const cycleFrac = phase === "in" ? 1 - (phaseLeft - 1) / PHASE_IN : (phaseLeft - 1) / PHASE_OUT;
  const scale = calm ? 0.8 : 0.62 + 0.38 * cycleFrac;
  const r = 108;

  return (
    <PageShell title="Restore" crumb="Aurora" bodyName="Aurora" maxW="max-w-[900px]">
      <div className="mx-auto max-w-2xl space-y-4">
        <div>
          <p className="label-eyebrow">Aurora · Calm mode</p>
          <h1 className="font-display mt-0.5 text-[22px] font-medium text-moonlight">Restore</h1>
          <p className="mt-1 text-[13px] leading-relaxed text-regolith">
            Follow the small body as it travels its orbit — expand as it swells
            (4 counts), release as it settles (6 counts). There is nothing to
            get right here.
          </p>
        </div>

        <div className="glass relative overflow-hidden rounded-panel">
          {/* nebula backdrop (lazy, procedural fallback) */}
          <SmartImage
            src="/assets/space/nebula-carina.jpg"
            alt=""
            className="absolute inset-0 h-full w-full object-cover opacity-40"
            disabled={prefs.reduceEffects}
          />
          <div className="absolute inset-0 bg-gradient-to-b from-void/40 via-transparent to-void/80" aria-hidden />

          <div className="relative flex flex-col items-center px-4 py-10">
            {/* breathing orbit */}
            <svg
              viewBox="0 0 260 260"
              className="h-64 w-64"
              role="img"
              aria-label={`Breathing guide: ${phase === "in" ? "breathe in" : "breathe out"}, ${phaseLeft} ${phaseLeft === 1 ? "count" : "counts"} remaining.`}
              aria-live="polite"
            >
              <circle cx="130" cy="130" r={r} fill="none" stroke="rgba(125,232,200,0.35)" strokeWidth="1.2" strokeDasharray="2 5" />
              <circle cx="130" cy="130" r={r - 14} fill="none" stroke="rgba(155,140,255,0.22)" strokeWidth="0.8" />
              {/* trail */}
              <circle
                cx="130"
                cy={130 - r}
                r="34"
                fill="url(#breath-body)"
                transform={`scale(${scale})`}
                style={{ transformOrigin: "130px " + (130 - r) + "px", transition: calm ? "none" : "transform 1s ease-in-out" }}
              />
              <defs>
                <radialGradient id="breath-body" cx="40%" cy="35%" r="80%">
                  <stop offset="0%" stopColor="#eafff6" />
                  <stop offset="55%" stopColor="#7de8c8" />
                  <stop offset="100%" stopColor="#5a3f9e" />
                </radialGradient>
              </defs>
              <circle cx="130" cy="130" r="2.4" fill="rgba(232,237,242,0.6)" />
            </svg>

            <p className="font-display mt-4 text-[20px] text-moonlight" aria-hidden>
              {phase === "in" ? "Breathe in…" : "Breathe out…"}
            </p>
            <p className="tnum mt-1 text-[13px] text-regolith">
              {phase === "in" ? "Expand — " : "Settle — "}
              {phaseLeft} {phaseLeft === 1 ? "count" : "counts"}
            </p>

            <div className="mt-6 flex flex-wrap items-center justify-center gap-2.5">
              <button
                type="button"
                onClick={() => setRunning((v) => !v)}
                aria-pressed={running}
                className="motion-fade inline-flex min-h-[44px] items-center gap-2 rounded-full border border-aurora/50 bg-aurora/10 px-4 text-[13px] text-aurora hover:bg-aurora/20"
              >
                {running ? <Pause size={14} aria-hidden /> : <Play size={14} aria-hidden />}
                {running ? "Pause guide" : "Resume guide"}
              </button>
              <button
                type="button"
                onClick={() => setAudioOn((v) => !v)}
                aria-pressed={audioOn}
                aria-label="Ambient sound (off by default)"
                className="motion-fade inline-flex min-h-[44px] items-center gap-2 rounded-full border border-hairline px-4 text-[12px] text-regolith hover:text-moonlight"
              >
                {audioOn ? <Volume2 size={14} aria-hidden /> : <VolumeX size={14} aria-hidden />}
                Ambient {audioOn ? "on" : "off"}
              </button>
            </div>
          </div>
        </div>

        <p className="text-center text-[11px] text-ink">
          A wellness pause, not a treatment. If something feels wrong, say so — the
          medical team is a relay away.
        </p>
      </div>
    </PageShell>
  );
}
