import { useSyncExternalStore } from "react";

/**
 * Tiny persisted preference store, shared across pages.
 * Values live in localStorage so they survive reloads (the console is
 * expected to run offline; storage failures degrade gracefully).
 */
export interface Prefs {
  /** Swap the Hub scene for a plain list of destinations. */
  simpleNav: boolean;
  /** Turn off ambient animation, backdrop blur and heavy imagery. */
  reduceEffects: boolean;
}

const KEY = "cg:prefs";
const DEFAULTS: Prefs = {
  simpleNav: false,
  reduceEffects:
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches,
};

function read(): Prefs {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return DEFAULTS;
    return { ...DEFAULTS, ...(JSON.parse(raw) as Partial<Prefs>) };
  } catch {
    return DEFAULTS;
  }
}

let prefs: Prefs = read();
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

export function setPref<K extends keyof Prefs>(key: K, value: Prefs[K]) {
  prefs = { ...prefs, [key]: value };
  try {
    window.localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {
    /* storage unavailable — session-only */
  }
  emit();
}

export function usePrefs(): { prefs: Prefs; setPref: typeof setPref } {
  const snapshot = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => prefs,
    () => DEFAULTS,
  );
  return { prefs: snapshot, setPref };
}
