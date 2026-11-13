import { useHealth } from "../HealthContext";
import { usePageTitle } from "../usePageTitle";
import { PageShell } from "../shell/PageShell";
import { SmartImage } from "../components/SmartImage";
import { usePrefs } from "../prefs";

/** Approximate mission length used for the "days to return" line. */
const MISSION_DAYS = 180;

/**
 * Earth view — the "Overview Effect" moment.
 * A calm full-disc Earth, a short grounding prompt, and the mission
 * distance in days: how far you've come, how close home is.
 */
export function EarthViewPage() {
  usePageTitle("Earth view");
  const health = useHealth();
  const { prefs } = usePrefs();
  const sinceLaunch = health.mission?.mission_day_index ?? 0;
  const toReturn = Math.max(0, MISSION_DAYS - sinceLaunch);

  return (
    <PageShell title="Earth view" crumb="Relay" bodyName="Relay" maxW="max-w-[900px]">
      <div className="mx-auto max-w-2xl space-y-4">
        <div>
          <p className="label-eyebrow">Relay · The link home</p>
          <h1 className="font-display mt-0.5 text-[22px] font-medium text-moonlight">Earth view</h1>
          <p className="mt-1 text-[12px] text-regolith">
            A quiet look at the whole picture. Comms messaging is a planned placeholder —
            this page is the grounding moment that ships today.
          </p>
        </div>

        <div className="glass relative overflow-hidden rounded-panel">
          <SmartImage
            src="/assets/space/earth-blue-marble.jpg"
            alt="Full-disc view of Earth, the Blue Marble, from space"
            className="aspect-[4/3] w-full object-cover sm:aspect-[16/10]"
            disabled={prefs.reduceEffects}
          />
          <div className="scrim absolute inset-0" aria-hidden />
          <div className="absolute inset-x-0 bottom-0 p-5 sm:p-6">
            <p className="tnum flex flex-wrap gap-x-5 gap-y-1 text-[12px]">
              <span className="text-regolith">
                Days since launch <span className="ml-1 text-[15px] text-moonlight">{sinceLaunch}</span>
              </span>
              <span className="text-regolith">
                Days to return <span className="ml-1 text-[15px] text-moonlight">{toReturn}</span>
              </span>
            </p>
            <p className="font-display mt-2 max-w-md text-[14px] leading-relaxed text-moonlight">
              Everything you miss, and everyone who misses you, is on that disc right now.
            </p>
            <p className="mt-1 text-[12px] leading-relaxed text-regolith">
              Let it be a slow breath, not a weight.
            </p>
          </div>
        </div>

        <div className="glass rounded-panel p-5">
          <p className="label-eyebrow">A 30-second grounding</p>
          <ol className="mt-2.5 space-y-1.5 text-[13px] leading-relaxed text-regolith">
            <li><span aria-hidden className="text-aurora">›</span> Look at the whole Earth — edges and all — for ten unhurried seconds.</li>
            <li><span aria-hidden className="text-aurora">›</span> Name one person you'll tell about today, when the relay opens.</li>
            <li><span aria-hidden className="text-aurora">›</span> If it helps, take one guided breath in the <a href="#/restore" className="text-aurora underline underline-offset-2">Aurora</a>.</li>
          </ol>
          <p className="mt-3 tnum text-[11px] text-ink">
            Relay status: {health.online ? "online — window open" : "offline — messages will queue"}
          </p>
        </div>

        <p className="text-center text-[11px] text-ink">
          Placeholder notice: direct Earth messaging (write-home) is planned but not yet
          built. The relay pill above reflects real connectivity state.
        </p>
      </div>
    </PageShell>
  );
}
