import type { GridCell, Meeting } from "./types";
import { clockIn, dayLabelIn } from "./tz";

/** Клетки сетки, попавшие во встречи: индекс клетки → встреча. Сравниваем моменты времени, пояс не важен. */
export function meetingCellKeys(cells: GridCell[], meetings: Meeting[]): Map<number, Meeting> {
  const result = new Map<number, Meeting>();
  if (meetings.length === 0) {
    return result;
  }
  const spans = meetings.map((meeting) => ({
    meeting,
    start: Date.parse(meeting.start),
    end: Date.parse(meeting.end),
  }));
  cells.forEach((cell, index) => {
    const cellStart = Date.parse(cell.start);
    const cellEnd = Date.parse(cell.end);
    const hit = spans.find((span) => span.start < cellEnd && span.end > cellStart);
    if (hit) {
      result.set(index, hit.meeting);
    }
  });
  return result;
}

/** «Чт 16.10, 16:00–17:00». */
export function meetingLabel(meeting: Meeting, tz: string): string {
  return `${dayLabelIn(meeting.start, tz)}, ${clockIn(meeting.start, tz)}–${clockIn(meeting.end, tz)}`;
}
