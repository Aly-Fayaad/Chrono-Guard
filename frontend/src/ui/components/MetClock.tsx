import { useMetClock } from "../hooks/useMetClock";

/** Mission Elapsed Time readout: D+014 07:42:10 */
export function MetClock() {
  const met = useMetClock();
  return (
    <time
      className="tnum text-[11px] text-regolith sm:text-[13px]"
      dateTime={met.replace("D+", "P").replace(/D\+\d+ /, "")}
      aria-label={`Mission elapsed time ${met}`}
    >
      <span className="text-earth/80">MET</span>{" "}
      <span className="text-moonlight">{met}</span>
    </time>
  );
}
