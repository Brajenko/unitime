const FALLBACK_TZ = "Europe/Moscow";
const DAY_LABELS: Record<string, string> = { пн: "Пн", вт: "Вт", ср: "Ср", чт: "Чт", пт: "Пт", сб: "Сб", вс: "Вс" };

/** Часовой пояс браузера: сетка и встречи показываются в нём. */
export const BROWSER_TZ = detectTz();

function detectTz(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || FALLBACK_TZ;
  } catch {
    return FALLBACK_TZ;
  }
}

export function clockIn(iso: string, tz: string): string {
  const parts = new Intl.DateTimeFormat("ru-RU", {
    timeZone: tz,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(new Date(iso));
  const hour = parts.find((part) => part.type === "hour")?.value ?? "00";
  const minute = parts.find((part) => part.type === "minute")?.value ?? "00";
  return `${hour === "24" ? "00" : hour}:${minute}`;
}

/** «Чт 16.10» — день недели и дата в заданном поясе. */
export function dayLabelIn(iso: string, tz: string): string {
  const parts = new Intl.DateTimeFormat("ru-RU", {
    timeZone: tz,
    weekday: "short",
    day: "numeric",
    month: "numeric",
  }).formatToParts(new Date(iso));
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  const weekday = get("weekday").toLowerCase().replace(".", "");
  return `${DAY_LABELS[weekday] ?? weekday} ${Number(get("day"))}.${Number(get("month"))}`;
}
