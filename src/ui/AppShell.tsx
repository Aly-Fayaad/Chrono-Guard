import type { ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { Activity, CalendarRange, ClipboardCheck, ListChecks } from "lucide-react";
import { OfflinePill } from "./components/OfflinePill";
import { MetClock } from "./components/MetClock";
import { useHealthData } from "./hooks/useHealthData";

export type NavKey = "today" | "checkin" | "schedule" | "guidance";

const NAV: { to: string; key: NavKey; label: string; icon: ReactNode }[] = [
  { to: "/", key: "today", label: "Today", icon: <Activity size={17} aria-hidden /> },
  { to: "/checkin", key: "checkin", label: "Check-in", icon: <ClipboardCheck size={17} aria-hidden /> },
  { to: "/schedule", key: "schedule", label: "Schedule", icon: <CalendarRange size={17} aria-hidden /> },
  { to: "/guidance", key: "guidance", label: "Guidance", icon: <ListChecks size={17} aria-hidden /> },
];

const railItem =
  "motion-fade relative flex h-11 items-center gap-3 rounded-md px-3 text-[13px] text-regolith hover:bg-raised hover:text-moonlight aria-[current=page]:bg-raised aria-[current=page]:text-earth";

/** Thin curved lunar-horizon line under the header. */
function HorizonArc() {
  return (
    <svg
      className="pointer-events-none absolute inset-x-0 -bottom-px h-8 w-full"
      viewBox="0 0 1200 32"
      preserveAspectRatio="none"
      aria-hidden
    >
      <path
        d="M0 30 Q 600 -14 1200 30"
        fill="none"
        stroke="rgba(200,215,230,0.16)"
        strokeWidth="1"
      />
      <path
        d="M0 30 Q 600 -14 1200 30"
        fill="none"
        stroke="rgba(76,154,255,0.25)"
        strokeWidth="1"
        strokeDasharray="1 6"
      />
    </svg>
  );
}

function Rail() {
  return (
    <nav
      aria-label="Primary"
      className="sticky top-0 hidden h-screen shrink-0 flex-col gap-1 border-r border-hairline bg-panel px-2 py-4 md:flex md:w-[72px] lg:w-[220px]"
    >
      <div className="mb-4 flex items-center gap-2.5 px-2">
        <span
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-earth/40 bg-raised font-mono text-[11px] text-earth"
          aria-hidden
        >
          CG
        </span>
        <span className="hidden font-mono text-[12px] tracking-[0.18em] text-moonlight lg:inline">
          CHRONOGUARD
        </span>
      </div>
      {NAV.map((n) => (
        <NavLink key={n.key} to={n.to} end={n.to === "/"} className={railItem} title={n.label}>
          {n.icon}
          <span className="hidden lg:inline">{n.label}</span>
        </NavLink>
      ))}
      <p className="mt-auto hidden px-3 font-mono text-[10px] leading-relaxed text-ink lg:inline">
        CREW DEMO-01
        <br />
        HAB DECK A · LUN-4
      </p>
    </nav>
  );
}

function BottomBar() {
  const location = useLocation();
  return (
    <nav
      aria-label="Primary"
      className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-4 border-t border-hairline bg-panel pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      {NAV.map((n) => {
        const isActive = n.to === "/" ? location.pathname === "/" : location.pathname.startsWith(n.to);
        return (
          <NavLink
            key={n.key}
            to={n.to}
            end={n.to === "/"}
            aria-current={isActive ? "page" : undefined}
            className={`motion-fade flex min-h-[56px] flex-col items-center justify-center gap-1 py-2 text-[10px] ${
              isActive ? "text-earth" : "text-regolith"
            }`}
          >
            {n.icon}
            {n.label}
          </NavLink>
        );
      })}
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { online, queued } = useHealthData();
  return (
    <div className="flex min-h-screen">
      <Rail />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="relative flex h-14 items-center justify-between gap-3 border-b border-hairline bg-panel px-4 sm:px-6">
          <div className="flex items-center gap-3 md:hidden">
            <span
              className="flex h-8 w-8 items-center justify-center rounded-md border border-earth/40 bg-raised font-mono text-[11px] text-earth"
              aria-hidden
            >
              CG
            </span>
            <span className="font-mono text-[12px] tracking-[0.18em] text-moonlight">
              CHRONOGUARD
            </span>
          </div>
          <p className="label-eyebrow hidden md:block">Lunar crew health console</p>
          <div className="flex items-center gap-3">
            <MetClock />
            <OfflinePill online={online} queued={queued} />
          </div>
          <HorizonArc />
        </header>
        <main className="mx-auto w-full max-w-[1200px] flex-1 px-4 pb-28 pt-5 sm:px-6 md:pb-10">
          {children}
        </main>
      </div>
      <BottomBar />
    </div>
  );
}
