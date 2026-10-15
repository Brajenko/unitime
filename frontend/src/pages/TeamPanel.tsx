import { FormEvent, useState } from "react";
import { createTeam } from "../api";
import type { GridMember, Team } from "../types";

const STALE_MINUTES = 30;

export function TeamPanel({
  teams,
  teamId,
  members,
  onSelect,
  onCreated,
}: {
  teams: Team[];
  teamId: string | null;
  members: GridMember[];
  onSelect: (teamId: string | null) => void;
  onCreated: (team: Team) => void;
}) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const team = teams.find((item) => item.id === teamId) ?? null;

  function submit(event: FormEvent) {
    event.preventDefault();
    createTeam(name)
      .then((created) => {
        setName("");
        setError(null);
        onCreated(created);
      })
      .catch((reason: Error) => setError(reason.message));
  }

  return (
    <div className="team-panel">
      <p className="eyebrow">КОМАНДА</p>
      <select value={teamId ?? ""} onChange={(event) => onSelect(event.target.value || null)}>
        <option value="">Только я</option>
        {teams.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name}
          </option>
        ))}
      </select>
      {team ? (
        <div className="invite">
          <button
            type="button"
            className="text-btn"
            onClick={() => {
              setInviteOpen((open) => !open);
              setCopied(false);
            }}
          >
            {inviteOpen ? "Скрыть ссылку-приглашение" : "Показать ссылку-приглашение"}
          </button>
          {inviteOpen ? (
            <div className="invite-box">
              <input readOnly value={inviteUrl(team)} onFocus={(e) => e.target.select()} />
              <button type="button" className="text-btn" onClick={() => copyInvite(inviteUrl(team), setCopied)}>
                {copied ? "Скопировано" : "Копировать"}
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
      <ul className="source-list">
        {members.map((member) => (
          <li key={member.user_id} className="source-item">
            <span className={`status-mark ${memberStatus(member)}`} />
            <span>
              <span className="source-name">{member.email}</span>
              <span className="source-meta">{memberNote(member)}</span>
            </span>
          </li>
        ))}
      </ul>
      <form className="team-create" onSubmit={submit}>
        <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Новая команда" required />
        <button type="submit" className="text-btn">
          Создать
        </button>
      </form>
      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}

function inviteUrl(team: Team): string {
  return `${window.location.origin}/join/${team.invite_token}`;
}

function copyInvite(url: string, setCopied: (value: boolean) => void) {
  navigator.clipboard
    .writeText(url)
    .then(() => setCopied(true))
    .catch(() => setCopied(false));
}

function memberStatus(member: GridMember): string {
  if (!member.in_overlay) {
    return "status-pending";
  }
  return isStale(member.last_synced_at) ? "status-auth_failed" : "status-active";
}

function memberNote(member: GridMember): string {
  if (!member.in_overlay) {
    return "нет календарей";
  }
  if (!member.last_synced_at) {
    return `${member.calendars} календ. · ещё не обновлялось`;
  }
  return `${member.calendars} календ. · обновлено ${agoLabel(member.last_synced_at)}`;
}

function isStale(iso: string | null): boolean {
  return !iso || Date.now() - Date.parse(iso) > STALE_MINUTES * 60000;
}

function agoLabel(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));
  if (minutes < 1) {
    return "только что";
  }
  if (minutes < 60) {
    return `${minutes} мин назад`;
  }
  const hours = Math.floor(minutes / 60);
  return hours < 24 ? `${hours} ч назад` : `${Math.floor(hours / 24)} дн назад`;
}
