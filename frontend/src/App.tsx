import { lazy, Suspense, useEffect, useMemo } from "react";
import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { HealthContext } from "./ui/HealthContext";
import { useHealthData } from "./ui/hooks/useHealthData";
import { usePrefs } from "./ui/prefs";
import { HubPage } from "./ui/shell/hub/HubPage";

// Inner pages are code-split so the Hub's first paint stays lean
// (recharts + charts only load when a destination is opened).
const TodayPage = lazy(() => import("./ui/pages/TodayPage").then((m) => ({ default: m.TodayPage })));
const CheckInPage = lazy(() => import("./ui/pages/CheckInPage").then((m) => ({ default: m.CheckInPage })));
const SchedulePage = lazy(() => import("./ui/pages/SchedulePage").then((m) => ({ default: m.SchedulePage })));
const GuidancePage = lazy(() => import("./ui/pages/GuidancePage").then((m) => ({ default: m.GuidancePage })));
const RestorePage = lazy(() => import("./ui/pages/RestorePage").then((m) => ({ default: m.RestorePage })));
const EarthViewPage = lazy(() => import("./ui/pages/EarthViewPage").then((m) => ({ default: m.EarthViewPage })));
const CreditsPage = lazy(() => import("./ui/pages/CreditsPage").then((m) => ({ default: m.CreditsPage })));

function PageFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center" role="status" aria-label="Loading page">
      <p className="tnum text-[13px] text-regolith">Traveling…</p>
    </div>
  );
}

/** Applies the global Reduce-effects class (stops ambient animation, blur, imagery). */
function EffectsController() {
  const { prefs } = usePrefs();
  useEffect(() => {
    document.documentElement.classList.toggle("reduce-effects", prefs.reduceEffects);
    document.body.dataset.hidden = "false";
    const onVis = () => {
      document.body.dataset.hidden = String(document.hidden);
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, [prefs.reduceEffects]);
  return null;
}

export default function App() {
  // One health-data source for the whole app (mock-aware via ?mock=).
  const health = useHealthData();
  const ctx = useMemo(() => health, [health]);

  return (
    <HealthContext.Provider value={ctx}>
      <EffectsController />
      <HashRouter>
        <Suspense fallback={<PageFallback />}>
          <Routes>
            <Route path="/" element={<HubPage />} />
            <Route path="/today" element={<TodayPage />} />
            <Route path="/check-in" element={<CheckInPage />} />
            {/* old deep link kept working */}
            <Route path="/checkin" element={<Navigate to="/check-in" replace />} />
            <Route path="/schedule" element={<SchedulePage />} />
            <Route path="/guidance" element={<GuidancePage />} />
            <Route path="/restore" element={<RestorePage />} />
            <Route path="/earth" element={<EarthViewPage />} />
            <Route path="/credits" element={<CreditsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </HashRouter>
    </HealthContext.Provider>
  );
}
