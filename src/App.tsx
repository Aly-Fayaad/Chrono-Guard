import { HashRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "./ui/AppShell";
import { useHealthData } from "./ui/hooks/useHealthData";
import { TodayPage } from "./ui/pages/TodayPage";
import { CheckInPage } from "./ui/pages/CheckInPage";
import { SchedulePage } from "./ui/pages/SchedulePage";
import { GuidancePage } from "./ui/pages/GuidancePage";

export default function App() {
  const health = useHealthData();
  return (
    <HashRouter>
      <AppShell>
        <Routes>
          <Route path="/" element={<TodayPage health={health} />} />
          <Route path="/checkin" element={<CheckInPage health={health} />} />
          <Route path="/schedule" element={<SchedulePage health={health} />} />
          <Route path="/guidance" element={<GuidancePage health={health} />} />
        </Routes>
      </AppShell>
    </HashRouter>
  );
}
