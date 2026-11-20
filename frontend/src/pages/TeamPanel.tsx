import { useState } from "react";
import { memberMark, memberNote, memberSummary, sortMembers } from "../members";
import { meetingLabel } from "../meetings";
import type { GridMember, Meeting, Team } from "../types";

export function TeamPanel({
  team,
  members,
  meetings,
  tz,
  onCancelMeeting,
}: {
  team: Team | null;
  members: GridMember[];
  meetings: Meeting[];
  tz: string;
  onCancelMeeting: (meeting: Meeting) => void;
}) {
  const [inviteOpen, setInviteOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const summary = memberSummary(members);
  const now = Date.now();

  if (!team) {
    return (
      <section className="panel-block">
        <p className="eyebrow">КОМАНДА</p>
        <p className="muted empty-note">
          Сейчас показана только ваша занятость. Выберите команду вверху или создайте новую и пригласите участников.
        </p>
      </section>
    );
  }

  return (
    <>
      <section className="panel-block">
        <p className="eyebrow">
          КОМАНДА · {summary.counted} из {summary.total} учтены
        </p>
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
        <button
          type="button"
          className="secondary"
          onClick={() => {
            setInviteOpen(true);
            copyInvite(inviteUrl(team), setCopied);
          }}
        >
          {copied ? "Ссылка скопирована" : "Пригласить"}
        </button>
        {inviteOpen ? (
          <input
            className="invite-input"
            readOnly
            value={inviteUrl(team)}
            onFocus={(event) => event.target.select()}
          />
        ) : null}
      </section>
      <section className="panel-block">
        <p className="eyebrow">ВСТРЕЧИ</p>
        {meetings.length === 0 ? (
          <p className="muted empty-note">Пока нет встреч. Нажмите на зелёный слот на сетке, чтобы назначить.</p>
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
      </section>
    </>
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
