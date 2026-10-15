import { useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation, useSearchParams } from "react-router-dom";
import { fetchMe } from "./api";
import type { User } from "./types";
import { AuthPage } from "./pages/AuthPage";
import { ConnectWizard } from "./pages/ConnectWizard";
import { JoinPage } from "./pages/JoinPage";
import { WeekGrid } from "./pages/WeekGrid";

const TEAM_KEY = "slot-team-id";

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const location = useLocation();

  const refreshUser = useCallback(() => {
    return fetchMe()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setReady(true));
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const handleLogout = useCallback(() => setUser(null), []);

  const rememberTeam = useCallback((teamId: string) => {
    try {
      window.localStorage.setItem(TEAM_KEY, teamId);
    } catch {
      // хранилище недоступно — команда просто не запомнится
    }
  }, []);

  if (!ready) {
    return null;
  }
  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<AuthPage onAuthed={refreshUser} />} />
        <Route path="*" element={<Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />} />
      </Routes>
    );
  }
  return (
    <Routes>
      <Route path="/" element={<WeekGrid user={user} onLogout={handleLogout} teamKey={TEAM_KEY} />} />
      <Route path="/connect" element={<ConnectWizard />} />
      <Route path="/login" element={<LoginRedirect />} />
      <Route path="/join/:token" element={<JoinPage onJoined={rememberTeam} />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function LoginRedirect() {
  const [params] = useSearchParams();
  return <Navigate to={safeNext(params.get("next"))} replace />;
}

function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/login")) {
    return "/";
  }
  return raw;
}
