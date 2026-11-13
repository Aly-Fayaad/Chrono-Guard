import { Wifi, WifiOff } from "lucide-react";

/**
 * Connectivity indicator. Never relies on color alone: it pairs a solid
 * status LED with an icon and a text label.
 */
export function OfflinePill({ online, queued }: { online: boolean; queued: number }) {
  return (
    <span
      className={`motion-fade inline-flex h-9 items-center gap-1.5 rounded-full border px-2.5 text-[11px] sm:h-11 sm:gap-2 sm:px-3 sm:text-[12px] ${
        online
          ? "border-nominal/30 text-nominal"
          : "border-watch/40 text-watch"
      }`}
      role="status"
      aria-label={online ? "Online" : `Offline, ${queued} entries queued for sync`}
    >
      <span className="relative inline-flex h-2 w-2">
        <span
          className={`absolute inset-0 rounded-full ring-1 ${
            online ? "bg-nominal ring-nominal/40" : "bg-watch ring-watch/40"
          }`}
        />
      </span>
      {online ? <Wifi size={13} aria-hidden /> : <WifiOff size={13} aria-hidden />}
      <span className="tnum">{online ? "Online" : `Offline · ${queued} queued`}</span>
    </span>
  );
}
