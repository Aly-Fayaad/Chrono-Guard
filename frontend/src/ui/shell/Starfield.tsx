import { useEffect, useRef } from "react";

/**
 * Procedural deep-space starfield on <canvas>.
 * - 3 parallax layers drifting very slowly (no user motion required)
 * - optional soft aurora band whose color/intensity follows crew status
 * - pauses when the tab is hidden, honors prefers-reduced-motion and the
 *   in-app "reduce effects" toggle (renders a single static frame).
 */
export function Starfield({
  density = 1,
  auroraColor = "#3dd6b0",
  auroraAlpha = 0.4,
  intensity = 1,
  staticOnly = false,
}: {
  /** 0..1 star density multiplier */
  density?: number;
  /** aurora tint */
  auroraColor?: string;
  /** 0..1 aurora strength */
  auroraAlpha?: number;
  /** 0..1 overall presence (inner pages run dimmer than the Hub) */
  intensity?: number;
  /** true → render one frame, no animation loop */
  staticOnly?: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const propsRef = useRef({ density, auroraColor, auroraAlpha, intensity });
  propsRef.current = { density, auroraColor, auroraAlpha, intensity };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduced =
      staticOnly ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let raf = 0;
    let disposed = false;

    interface Star {
      x: number;
      y: number;
      r: number;
      layer: number;
      tw: number;
      twPhase: number;
    }
    let stars: Star[] = [];
    let w = 0;
    let h = 0;
    let dpr = 1;

    function seed() {
      const rect = canvas!.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = rect.width;
      h = rect.height;
      canvas!.width = Math.max(1, Math.round(w * dpr));
      canvas!.height = Math.max(1, Math.round(h * dpr));
      const area = (w * h) / 1000;
      const count = Math.round(area * 0.9 * propsRef.current.density * propsRef.current.intensity);
      stars = [];
      for (let i = 0; i < count; i++) {
        const layer = i % 3; // 0 far, 1 mid, 2 near
        stars.push({
          x: Math.random() * w,
          y: Math.random() * h,
          r: layer === 0 ? 0.5 : layer === 1 ? 0.8 : 1.15,
          layer,
          tw: 0.4 + Math.random() * 0.6,
          twPhase: Math.random() * Math.PI * 2,
        });
      }
    }

    function draw(t: number) {
      const { auroraColor: ac, auroraAlpha: aa, intensity: it } = propsRef.current;
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx!.clearRect(0, 0, w, h);

      // Aurora — two soft radial glows, low alpha, near the lower third.
      if (aa > 0.01) {
        for (const [cx, cy, rr, a] of [
          [w * 0.22, h * 0.85, Math.max(w, h) * 0.42, 0.9],
          [w * 0.72, h * 0.72, Math.max(w, h) * 0.5, 0.65],
        ] as const) {
          const g = ctx!.createRadialGradient(cx, cy, 0, cx, cy, rr);
          g.addColorStop(0, hexA(ac, aa * a * it));
          g.addColorStop(1, "rgba(0,0,0,0)");
          ctx!.fillStyle = g;
          ctx!.fillRect(0, 0, w, h);
        }
      }

      // Stars
      for (const s of stars) {
        const drift = reduced ? 0 : t * 0.0000042 * (s.layer + 1);
        const x = (s.x - drift * (s.layer + 1) * 14) % w;
        const twinkle = reduced
          ? 1
          : 0.75 + 0.25 * Math.sin(s.twPhase + t * 0.00035 * s.tw);
        ctx!.globalAlpha = twinkle * (0.28 + 0.24 * s.layer) * it;
        ctx!.fillStyle = s.layer === 2 ? "#dfe8f2" : "#aebccb";
        ctx!.beginPath();
        ctx!.arc(x < 0 ? x + w : x, s.y, s.r, 0, Math.PI * 2);
        ctx!.fill();
      }
      ctx!.globalAlpha = 1;
    }

    let start: number | null = null;
    function loop(now: number) {
      if (disposed) return;
      if (start === null) start = now;
      // ~30fps is plenty for slow ambient drift
      if (now - start >= 33) {
        start = now;
        draw(now);
      }
      raf = requestAnimationFrame(loop);
    }

    seed();
    draw(0);
    if (!reduced) raf = requestAnimationFrame(loop);

    const onResize = () => {
      seed();
      draw(performance.now());
    };
    window.addEventListener("resize", onResize);

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
    };
  }, [staticOnly]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 h-full w-full"
    />
  );
}

/** hex → rgba() helper */
function hexA(hex: string, alpha: number): string {
  const n = hex.replace("#", "");
  const v = n.length === 3 ? n.split("").map((c) => c + c).join("") : n;
  const r = parseInt(v.slice(0, 2), 16);
  const g = parseInt(v.slice(2, 4), 16);
  const b = parseInt(v.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha.toFixed(3)})`;
}
