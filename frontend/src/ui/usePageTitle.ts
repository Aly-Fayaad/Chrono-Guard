import { useEffect } from "react";

/** Set the browser tab title per route. */
export function usePageTitle(title: string) {
  useEffect(() => {
    const prev = document.title;
    document.title = `${title} — ChronoGuard`;
    return () => {
      document.title = prev;
    };
  }, [title]);
}
