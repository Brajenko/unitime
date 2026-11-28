const MONTHS_GENITIVE = [
  "января",
  "февраля",
  "марта",
  "апреля",
  "мая",
  "июня",
  "июля",
  "августа",
  "сентября",
  "октября",
  "ноября",
  "декабря",
];

/** Сдвиг диапазона дат на его же длину вперёд (+1) или назад (-1): «следующая/предыдущая неделя». */
export function shiftRange(dateFrom: string, dateTo: string, direction: 1 | -1): { dateFrom: string; dateTo: string } {
  const from = parse(dateFrom);
  const to = parse(dateTo);
  const span = Math.round((to.getTime() - from.getTime()) / 86400000) + 1;
  from.setDate(from.getDate() + direction * span);
  to.setDate(to.getDate() + direction * span);
  return { dateFrom: format(from), dateTo: format(to) };
}

/** «23–29 ноября», «30 ноября – 6 декабря», «28 декабря 2026 – 3 января 2027». */
export function rangeLabel(dateFrom: string, dateTo: string): string {
  const from = parse(dateFrom);
  const to = parse(dateTo);
  const sameYear = from.getFullYear() === to.getFullYear();
  const end = `${to.getDate()} ${MONTHS_GENITIVE[to.getMonth()]}${sameYear ? "" : ` ${to.getFullYear()}`}`;
  if (dateFrom === dateTo) {
    return end;
  }
  if (sameYear && from.getMonth() === to.getMonth()) {
    return `${from.getDate()}–${end}`;
  }
  const start = `${from.getDate()} ${MONTHS_GENITIVE[from.getMonth()]}${sameYear ? "" : ` ${from.getFullYear()}`}`;
  return `${start} – ${end}`;
}

function parse(value: string): Date {
  return new Date(`${value}T12:00:00`);
}

function format(value: Date): string {
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${value.getFullYear()}-${month}-${day}`;
}
