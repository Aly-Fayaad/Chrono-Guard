import { Link, useLocation } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { CelestialBody } from "./CelestialBody";
import { HUB_BODIES } from "./hub/hubBodies";

/**
 * Compact orbit-style nav for inner pages: small celestial bodies in a row,
 * current destination slightly brighter. Replaces the old sidebar.
 */
export function MiniOrbitNav({ accent }: { accent?: string }) {
  const { pathname } = useLocation();
  return (
    <nav aria-label="Destinations" className="flex items-center gap-1.5">
      <Link
        to="/"
        className="motion-fade inline-flex min-h-[44px] items-center gap-1.5 rounded-full border border-hairline px-3 text-[12px] text-regolith hover:border-earth/50 hover:text-earth"
        aria-label="Return to Hub"
      >
        <ArrowLeft size={13} aria-hidden />
        <span className="hidden sm:inline">Hub</span>
      </Link>
      <span aria-hidden className="mx-1 h-4 w-px bg-hairline" />
      <ul className="flex items-center gap-0.5">
        {HUB_BODIES.map((b) => {
          const active = pathname.startsWith(b.path);
          return (
            <li key={b.key}>
              <Link
                to={b.path}
                aria-label={b.ariaLabel}
                aria-current={active ? "page" : undefined}
                title={`${b.name} — ${b.breadcrumb}`}
                className={`motion-fade inline-flex h-11 w-11 items-center justify-center rounded-full transition hover:bg-raised/60 ${
                  active ? "bg-raised/80" : ""
                }`}
              >
                <CelestialBody
                  kind={b.kind}
                  size={active ? 24 : 19}
                  statusColor={active ? accent : undefined}
                />
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
