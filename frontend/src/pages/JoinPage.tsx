import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { joinTeam } from "../api";

export function JoinPage({ onJoined }: { onJoined: (teamId: string) => void }) {
  const { token } = useParams();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      return;
    }
    joinTeam(token)
      .then((team) => {
        onJoined(team.id);
        navigate("/", { replace: true });
      })
      .catch((reason: Error) => setError(reason.message));
  }, [token, navigate, onJoined]);

  return (
    <div className="page">
      <div className="card wizard">
        <p className="eyebrow">ПРИГЛАШЕНИЕ</p>
        {error ? <p className="error">{error}</p> : <p className="muted">Добавляем вас в команду…</p>}
      </div>
    </div>
  );
}
