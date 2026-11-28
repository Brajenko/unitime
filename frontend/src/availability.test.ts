import { describe, expect, it } from "vitest";
import { cellsToWindows, paintRect, windowsForSave, windowsToCellSet } from "./availability";
import type { GridCell } from "./types";

// день 0: 09–13 UTC, день 1: 09–13 UTC, шаг час
function cell(dayIndex: number, hour: number): GridCell {
  const day = dayIndex === 0 ? "2026-12-02" : "2026-12-03";
  const start = new Date(`${day}T${String(hour).padStart(2, "0")}:00:00Z`);
  return {
    day_index: dayIndex,
    day,
    hour,
    minute: 0,
    free_count: 1,
    total: 1,
    start: start.toISOString(),
    end: new Date(start.getTime() + 3600000).toISOString(),
    slot_start: false,
    in_slot: false,
  };
}

const cells = [0, 1].flatMap((day) => [9, 10, 11, 12].map((hour) => cell(day, hour)));
// индексы: день 0 → 0..3 (9,10,11,12), день 1 → 4..7

describe("cellsToWindows", () => {
  it("склеивает подряд идущие клетки одного дня", () => {
    expect(cellsToWindows(cells, new Set([0, 1, 3]))).toEqual([
      { start: "2026-12-02T09:00:00.000Z", end: "2026-12-02T11:00:00.000Z" },
      { start: "2026-12-02T12:00:00.000Z", end: "2026-12-02T13:00:00.000Z" },
    ]);
  });

  it("не склеивает разные дни, порядок выбора не важен", () => {
    expect(cellsToWindows(cells, new Set([4, 3]))).toEqual([
      { start: "2026-12-02T12:00:00.000Z", end: "2026-12-02T13:00:00.000Z" },
      { start: "2026-12-03T09:00:00.000Z", end: "2026-12-03T10:00:00.000Z" },
    ]);
  });

  it("пустой выбор — пустой список", () => {
    expect(cellsToWindows(cells, new Set())).toEqual([]);
  });
});

describe("windowsToCellSet", () => {
  it("туда и обратно даёт тот же набор клеток", () => {
    const picked = new Set([0, 1, 3, 5, 6]);
    expect(windowsToCellSet(cells, cellsToWindows(cells, picked))).toEqual(picked);
  });

  it("окно, частично покрывающее клетку, её не отмечает; пояс в строке не важен", () => {
    const found = windowsToCellSet(cells, [{ start: "2026-12-02T12:30:00+03:00", end: "2026-12-02T14:30:00+03:00" }]);
    // 09:30–11:30 UTC: целиком покрыта только клетка 10:00
    expect([...found]).toEqual([1]);
  });
});

describe("windowsForSave", () => {
  it("окна вне видимых часов сохраняются, внутри — заменяются разметкой", () => {
    const original = [
      { start: "2026-12-02T07:00:00Z", end: "2026-12-02T10:00:00Z" }, // 07–09 вне сетки, 09–10 внутри
      { start: "2026-12-02T11:00:00Z", end: "2026-12-02T12:00:00Z" }, // внутри, снято пользователем
      { start: "2026-12-05T10:00:00Z", end: "2026-12-05T11:00:00Z" }, // другой день, вне сетки
    ];
    const result = windowsForSave(cells, original, new Set([4]));
    expect(result).toEqual([
      { start: "2026-12-02T07:00:00.000Z", end: "2026-12-02T09:00:00.000Z" },
      { start: "2026-12-03T09:00:00.000Z", end: "2026-12-03T10:00:00.000Z" },
      { start: "2026-12-05T10:00:00.000Z", end: "2026-12-05T11:00:00.000Z" },
    ]);
  });

  it("исходные окна обрезаются по диапазону сохранения", () => {
    const range = { start: Date.parse("2026-12-02T00:00:00Z"), end: Date.parse("2026-12-04T00:00:00Z") };
    const original = [{ start: "2026-12-01T22:00:00Z", end: "2026-12-02T02:00:00Z" }];
    expect(windowsForSave(cells, original, new Set(), range)).toEqual([
      { start: "2026-12-02T00:00:00.000Z", end: "2026-12-02T02:00:00.000Z" },
    ]);
  });

  it("без исходных окон отправляется только разметка", () => {
    expect(windowsForSave(cells, [], new Set([0, 1]))).toEqual([
      { start: "2026-12-02T09:00:00.000Z", end: "2026-12-02T11:00:00.000Z" },
    ]);
  });
});

describe("paintRect", () => {
  it("отмечает прямоугольник по дням и времени", () => {
    // от день0 10:00 (1) до день1 11:00 (6)
    expect([...paintRect(cells, new Set(), 1, 6, true)].sort()).toEqual([1, 2, 5, 6]);
  });

  it("если потянуть обратно, клетки вне прямоугольника возвращаются к исходному состоянию", () => {
    const snapshot = new Set([7]);
    const wide = paintRect(cells, snapshot, 0, 3, true);
    expect([...wide].sort()).toEqual([0, 1, 2, 3, 7]);
    const back = paintRect(cells, snapshot, 0, 1, true);
    expect([...back].sort()).toEqual([0, 1, 7]);
  });

  it("снятие отметки прямоугольником", () => {
    const all = new Set([0, 1, 2, 3, 4, 5, 6, 7]);
    expect([...paintRect(cells, all, 2, 7, false)].sort()).toEqual([0, 1, 4, 5]);
  });

  it("одна клетка при нажатии без протягивания", () => {
    expect([...paintRect(cells, new Set(), 5, 5, true)]).toEqual([5]);
  });
});
