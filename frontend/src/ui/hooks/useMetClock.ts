import { useEffect, useState } from "react";
import { metFull } from "../lib/time";

/** Ticks once per second and formats the mission elapsed time. */
export function useMetClock(): string {
  const [text, setText] = useState(() => metFull(new Date()));

  useEffect(() => {
    const id = window.setInterval(() => setText(metFull(new Date())), 1000);
    return () => window.clearInterval(id);
  }, []);

  return text;
}
