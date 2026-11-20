import { describe, expect, it } from "vitest";
import { meetingCellKeys, meetingLabel } from "./meetings";
import type { GridCell, Meeting } from "./types";

function cell(startIso: string, minutes = 60): GridCell {
  const start = new Date(startIso);
  const end = new Date(start.getTime() + minutes * 60000);
  return {
    day_index: 0,
    day: startIso.slice(0, 10),
    hour: start.getUTCHours(),
    minute: 0,
    free_count: 1,
    total: 1,
    start: start.toISOString(),
    end: end.toISOString(),
    slot_start: false,
    in_slot: false,
  };
}

function meeting(startIso: string, endIso: string): Meeting {
  return {
    id: "m1",
    team_id: "t1",
    start: startIso,
    end: endIso,
    title: "Синк",
    created_by_email: "a@example.com",
    can_cancel: true,
  };
}

const cells = [cell("2026-12-02T09:00:00Z"), cell("2026-12-02T10:00:00Z"), cell("2026-12-02T11:00:00Z"), cell("2026-12-02T12:00:00Z")];

describe("meetingCellKeys", () => {
  it("без встреч пусто", () => {
    expect(meetingCellKeys(cells, []).size).toBe(0);
  });

  it("встреча на два часа покрывает две клетки", () => {
    const found = meetingCellKeys(cells, [meeting("2026-12-02T10:00:00Z", "2026-12-02T12:00:00Z")]);
    expect([...found.keys()]).toEqual([1, 2]);
  });

  it("встык с клеткой не считается пересечением", () => {
    const found = meetingCellKeys(cells, [meeting("2026-12-02T10:00:00Z", "2026-12-02T11:00:00Z")]);
    expect([...found.keys()]).toEqual([1]);
  });

  it("встреча внутри клетки попадает в неё, пояс в строке не мешает", () => {
    const found = meetingCellKeys(cells, [meeting("2026-12-02T13:15:00+03:00", "2026-12-02T13:45:00+03:00")]);
    expect([...found.keys()]).toEqual([1]);
  });

  it("встреча вне сетки ничего не отмечает", () => {
    expect(meetingCellKeys(cells, [meeting("2026-12-05T10:00:00Z", "2026-12-05T11:00:00Z")]).size).toBe(0);
  });
});

describe("meetingLabel", () => {
  it("форматирует день и время в поясе", () => {
    const item = meeting("2026-12-03T13:00:00Z", "2026-12-03T14:00:00Z");
    expect(meetingLabel(item, "Europe/Moscow")).toBe("Чт 3.12, 16:00–17:00");
  });
});
