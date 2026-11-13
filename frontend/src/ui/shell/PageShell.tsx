import { useEffect, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Sparkles, Eye } from "lucide-react";
import { OfflinePill } from "../components/OfflinePill";
import { MetClock } from "../components/MetClock";
import { useHealth } from "../HealthContext";
import { usePrefs } from "../prefs";
import { usePageTitle } from "../usePageTitle";
import { Starfield } from "./Starfield";
import { MiniOrbitNav } from "./MiniOrbitNav";

function ToggleButton({
  on,
  onClick,
  icon,
  children,
  ariaLabel,
}: {
  on: boolean;
  onClick: () => void;
  icon: ReactNode;
  children: ReactNode;
  ariaLabel: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      aria-label={ariaLabel}
      title={ariaLabel}
      className={`motion-fade inline-flex min-h-[44px] items-center gap-1.5 rounded-full border px-3 text-[11px] ${
        on
          ? "border-aurora/50 bg-aurora/10 text-aurora"
          : "border-hairline text-regolith hover:text-moonlight"
      }`}
    >
      {icon}
      <span className="hidden md:inline">{children}</span>
    </button>
  );
}

/**
 * Shell for all inner pages (everything reached from the Hub).
 * Low-intensity starfield, glass header with mini-orbit nav, breadcrumb,
 * MET clock, offline pill, global toggles, and a themed footer.
 * Esc always returns to the Hub.
 */
export function PageShell({
  title,
  crumb,
  bodyName,
  children,
  maxW = "max-w-[1200px]",
}: {
  title: string;
  /** middle breadcrumb segment, e.g. "Earth" */
  crumb: string;
  /** small celestial name for the header chip */
  bodyName: string;
  children: ReactNode;
  maxW?: string;
}) {
  usePageTitle(title);
  const { online, queued } = useHealth();
  const { prefs, setPref } = usePrefs();
  const navigate = useNavigate();

  // Esc returns to the Hub (unless the simple-nav preference — also fine).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") navigate("/");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);

  return (
    <div className="relative flex min-h-screen flex-col">
      <div className="pointer-events-none fixed inset-0 z-0">
        <Starfield
          density={0.55}
          auroraAlpha={0.16}
          intensity={0.6}
          staticOnly={prefs.reduceEffects}
        />
      </div>

      <header className="glass-soft sticky top-0 z-20 border-b border-hairline">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-x-4 gap-y-2 px-3 py-2 sm:px-6">
          <MiniOrbitNav />
          <nav aria-label="Breadcrumb" className="hidden items-center gap-1.5 text-[11px] text-regolith lg:flex">
            <Link to="/" className="hover:text-earth">Hub</Link>
            <span aria-hidden>›</span>
            <span aria-current="location" className="text-moonlight/80">{crumb}</span>
            <span aria-hidden>›</span>
            <span>{title}</span>
          </nav>
          <div className="flex items-center gap-2">
            <MetClock />
            <OfflinePill online={online} queued={queued} />
            <ToggleButton
              on={prefs.reduceEffects}
              onClick={() => setPref("reduceEffects", !prefs.reduceEffects)}
              icon={<Sparkles size={13} aria-hidden />}
              ariaLabel="Reduce effects: turn off animation and heavy imagery"
            >
              Reduce effects
            </ToggleButton>
            <ToggleButton
              on={prefs.simpleNav}
              onClick={() => setPref("simpleNav", !prefs.simpleNav)}
              icon={<Eye size={13} aria-hidden />}
              ariaLabel="Simple navigation: plain list instead of the hub scene"
            >
              Simple nav
            </ToggleButton>
          </div>
        </div>
      </header>

      <main
        key={title}
        className={`hub-fade-in relative z-10 mx-auto w-full flex-1 ${maxW} px-3 pb-16 pt-5 sm:px-6 sm:pt-6`}
      >
        {children}
      </main>

      <footer className="relative z-10 border-t border-hairline bg-void/70 px-4 py-4 sm:px-6">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-2 text-[11px] text-ink">
          <p>
            <span className="font-mono">{bodyName}</span> · CREW DEMO-01 · HAB DECK A · LUN-4
          </p>
          <p className="max-w-[520px] leading-relaxed">
            Imagery courtesy of NASA. ChronoGuard is not affiliated with or endorsed by
            NASA. <Link to="/credits" className="underline decoration-ink/50 underline-offset-2 hover:text-regolith">Image credits</Link>
          </p>
        </div>
      </footer>
    </div>
  );
}
