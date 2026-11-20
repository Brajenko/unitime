import type { AvailabilityWindow, GridCell } from "./types";

type Span = { start: number; end: number };

/** Клетки, целиком лежащие внутри свободных окон. Частично покрытая клетка не отмечается. */
export function windowsToCellSet(cells: GridCell[], windows: AvailabilityWindow[]): Set<number> {
  const spans = windows.map(toSpan);
  const result = new Set<number>();
  cells.forEach((cell, index) => {
    const start = Date.parse(cell.start);
    const end = Date.parse(cell.end);
    if (spans.some((span) => span.start <= start && span.end >= end)) {
      result.add(index);
    }
  });
  return result;
}

/** Отмеченные клетки → окна: подряд идущие клетки одного дня склеиваются в одно окно. */
export function cellsToWindows(cells: GridCell[], indexes: Set<number>): AvailabilityWindow[] {
  const sorted = [...indexes]
    .filter((index) => index >= 0 && index < cells.length)
    .sort((left, right) => Date.parse(cells[left].start) - Date.parse(cells[right].start));
  const windows: AvailabilityWindow[] = [];
  let current: { day: number; start: string; end: string } | null = null;
  for (const index of sorted) {
    const cell = cells[index];
    if (current && current.day === cell.day_index && Date.parse(current.end) === Date.parse(cell.start)) {
      current.end = cell.end;
      continue;
    }
    if (current) {
      windows.push({ start: current.start, end: current.end });
    }
    current = { day: cell.day_index, start: cell.start, end: cell.end };
  }
  if (current) {
    windows.push({ start: current.start, end: current.end });
  }
  return windows;
}

/**
 * Что отправить на сервер при сохранении. Сервер заменяет окна за целые дни,
 * поэтому сохранённые окна вне видимых часов сетки (другое «Время» в настройках)
 * сохраняем как есть, а внутри видимых часов берём текущую разметку.
 */
export function windowsForSave(
  cells: GridCell[],
  original: AvailabilityWindow[],
  selected: Set<number>,
  range?: { start: number; end: number },
): AvailabilityWindow[] {
  const visible = visibleSpans(cells);
  const kept = original
    .map(toSpan)
    .map((span) => (range ? { start: Math.max(span.start, range.start), end: Math.min(span.end, range.end) } : span))
    .filter((span) => span.end > span.start)
    .flatMap((span) => subtract(span, visible));
  const marked = cellsToWindows(cells, selected).map(toSpan);
  return [...kept, ...marked]
    .sort((left, right) => left.start - right.start)
    .map((span) => ({ start: new Date(span.start).toISOString(), end: new Date(span.end).toISOString() }));
}

function visibleSpans(cells: GridCell[]): Span[] {
  const byDay = new Map<number, Span>();
  cells.forEach((cell) => {
    const start = Date.parse(cell.start);
    const end = Date.parse(cell.end);
    const span = byDay.get(cell.day_index);
    byDay.set(cell.day_index, span ? { start: Math.min(span.start, start), end: Math.max(span.end, end) } : { start, end });
  });
  return [...byDay.values()];
}

function subtract(span: Span, holes: Span[]): Span[] {
  let pieces: Span[] = [span];
  for (const hole of holes) {
    pieces = pieces.flatMap((piece) => {
      if (hole.end <= piece.start || hole.start >= piece.end) {
        return [piece];
      }
      const rest: Span[] = [];
      if (hole.start > piece.start) {
        rest.push({ start: piece.start, end: hole.start });
      }
      if (hole.end < piece.end) {
        rest.push({ start: hole.end, end: piece.end });
      }
      return rest;
    });
  }
  return pieces;
}

function toSpan(window: AvailabilityWindow): Span {
  return { start: Date.parse(window.start), end: Date.parse(window.end) };
}
