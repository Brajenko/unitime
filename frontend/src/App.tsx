import { Navigate, Route, Routes } from "react-router-dom";
import { ConnectWizard } from "./pages/ConnectWizard";
import { WeekGrid } from "./pages/WeekGrid";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<WeekGrid />} />
      <Route path="/connect" element={<ConnectWizard />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
