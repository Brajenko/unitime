import type { GridMember } from "./types";

export type MemberSummary = {
  counted: number;
  total: number;
  /** Не попали в сетку: нет календарей или доступ потерян. */
  missing: GridMember[];
  /** В сетке, но данные давно не обновлялись. */
  stale: GridMember[];
};

export function memberSummary(members: GridMember[]): MemberSummary {
  const missing = members.filter((member) => member.status === "no_calendars" || member.status === "auth_failed");
  const stale = members.filter((member) => member.status === "stale");
  return { counted: members.length - missing.length, total: members.length, missing, stale };
}

/** Проблемные участники наверху, внутри групп порядок сохраняется. */
export function sortMembers(members: GridMember[]): GridMember[] {
  return [...members].sort((left, right) => Number(isFine(left)) - Number(isFine(right)));
}

function isFine(member: GridMember): boolean {
  return member.status === "ok" || member.status === "manual";
}

export function memberMark(member: GridMember): string {
  if (member.status === "ok" || member.status === "manual") {
    return "status-active";
  }
  if (member.status === "stale") {
    return "status-syncing";
  }
  return member.status === "auth_failed" ? "status-auth_failed" : "status-pending";
}

export function memberNote(member: GridMember, now: number): string {
  if (member.status === "no_calendars") {
    return "не подключил календарь";
  }
  if (member.status === "manual") {
    return "отметил окна вручную";
  }
  if (member.status === "auth_failed") {
    return "доступ к календарю потерян — нужно переподключить";
  }
  if (!member.last_synced_at) {
    return `${member.calendars} календ. · ещё не обновлялось`;
  }
  const ago = `обновлено ${agoLabel(member.last_synced_at, now)}`;
  return member.status === "stale"
    ? `${member.calendars} календ. · данные устарели, ${ago}`
    : `${member.calendars} календ. · ${ago}`;
}

export function agoLabel(iso: string, now: number): string {
  const minutes = Math.max(0, Math.round((now - Date.parse(iso)) / 60000));
  if (minutes < 1) {
    return "только что";
  }
  if (minutes < 60) {
    return `${minutes} мин назад`;
  }
  const hours = Math.floor(minutes / 60);
  return hours < 24 ? `${hours} ч назад` : `${Math.floor(hours / 24)} дн назад`;
}

export function missingNames(summary: MemberSummary): string {
  return summary.missing.map((member) => member.email).join(", ");
}
