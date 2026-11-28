import { FormEvent, useState } from "react";
import { createTeam } from "../api";
import type { Team, User } from "../types";

const NEW_TEAM = "__new__";

export function TopBar({
  user,
  teams,
  teamId,
  onSelect,
  onCreated,
  onLogout,
}: {
  user: User;
  teams: Team[];
  teamId: string | null;
  onSelect: (teamId: string | null) => void;
  onCreated: (team: Team) => void;
  onLogout: () => void;
}) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    createTeam(name)
      .then((created) => {
        setName("");
        setError(null);
        setCreating(false);
        onCreated(created);
      })
      .catch((reason: Error) => setError(reason.message));
  }

  return (
    <header className="topbar">
      <div className="topbar-team">
        {creating ? (
          <form className="team-create" onSubmit={submit}>
            <input
              autoFocus
              value={name}
              maxLength={128}
              onChange={(event) => setName(event.target.value)}
              placeholder="Название команды"
              required
            />
            <button type="submit" className="primary">
              Создать
            </button>
            <button
              type="button"
              className="text-btn"
              onClick={() => {
                setCreating(false);
                setError(null);
              }}
            >
              Отмена
            </button>
          </form>
        ) : (
          <select
            className="team-select"
            aria-label="Команда"
            value={teamId ?? ""}
            onChange={(event) => {
              if (event.target.value === NEW_TEAM) {
                setCreating(true);
                return;
              }
              onSelect(event.target.value || null);
            }}
          >
            <option value="">Только я</option>
            {teams.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
            <option value={NEW_TEAM}>+ Новая команда…</option>
          </select>
        )}
        {error ? <span className="error">{error}</span> : null}
      </div>
      <div className="topbar-user">
        <span className="muted">{user.email}</span>
        <button type="button" className="text-btn" onClick={onLogout}>
          Выйти
        </button>
      </div>
    </header>
  );
}
