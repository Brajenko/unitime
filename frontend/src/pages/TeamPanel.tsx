import { FormEvent, useState } from "react";
import { createTeam } from "../api";
import { memberMark, memberNote, memberSummary, sortMembers } from "../members";
import { meetingLabel } from "../meetings";
import type { GridMember, Meeting, Team } from "../types";

export function TeamPanel({
  teams,
  teamId,
  members,
  meetings,
  tz,
  onCancelMeeting,
  onSelect,
  onCreated,
}: {
  teams: Team[];
  teamId: string | null;
  members: GridMember[];
  meetings: Meeting[];
  tz: string;
  onCancelMeeting: (meeting: Meeting) => void;
  onSelect: (teamId: string | null) => void;
  onCreated: (team: Team) => void;
}) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const team = teams.find((item) => item.id === teamId) ?? null;
  const summary = memberSummary(members);
  const now = Date.now();

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
      {team ? (
        <p className={summary.missing.length > 0 ? "member-summary member-summary-warn" : "member-summary"}>
          Учтено в сетке: {summary.counted} из {summary.total}
          {summary.missing.length > 0 ? (
            <button type="button" className="text-btn" onClick={() => copyInvite(inviteUrl(team), setCopied)}>
              {copied ? "Ссылка скопирована" : "Скопировать приглашение"}
            </button>
          ) : null}
        </p>
      ) : null}
      <ul className="source-list">
        {sortMembers(members).map((member) => (
          <li key={member.user_id} className="source-item">
            <span className={`status-mark ${memberMark(member)}`} />
            <span>
              <span className="source-name">{member.email}</span>
              <span className="source-meta">{memberNote(member, now)}</span>
            </span>
          </li>
        ))}
      </ul>
      {team ? (
        <div className="meetings">
          <p className="eyebrow">ВСТРЕЧИ</p>
          {meetings.length === 0 ? (
            <p className="muted">Пока нет зафиксированных встреч. Нажмите на зелёный слот на сетке.</p>
          ) : (
            <ul className="source-list">
              {meetings.map((meeting) => (
                <li key={meeting.id} className="source-item">
                  <span className="status-mark status-meeting" />
                  <span className="source-text">
                    <span className="source-name">{meeting.title ?? "Встреча"}</span>
                    <span className="source-meta">
                      {meetingLabel(meeting, tz)} · {meeting.created_by_email}
                    </span>
                  </span>
                  {meeting.can_cancel ? (
                    <button
                      type="button"
                      className="source-remove"
                      title="Отменить встречу"
                      aria-label="Отменить встречу"
                      onClick={() => onCancelMeeting(meeting)}
                    >
                      ×
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
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
