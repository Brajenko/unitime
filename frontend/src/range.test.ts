import { describe, expect, it } from "vitest";
import { rangeLabel, shiftRange } from "./range";

describe("shiftRange", () => {
  it("листает неделю вперёд и назад", () => {
    expect(shiftRange("2026-11-23", "2026-11-29", 1)).toEqual({ dateFrom: "2026-11-30", dateTo: "2026-12-06" });
    expect(shiftRange("2026-11-23", "2026-11-29", -1)).toEqual({ dateFrom: "2026-11-16", dateTo: "2026-11-22" });
  });

  it("сдвигает на длину диапазона и через год", () => {
    expect(shiftRange("2026-12-28", "2026-12-30", 1)).toEqual({ dateFrom: "2026-12-31", dateTo: "2027-01-02" });
    expect(shiftRange("2026-11-20", "2026-11-20", -1)).toEqual({ dateFrom: "2026-11-19", dateTo: "2026-11-19" });
  });

  it("переход на летнее время не сбивает даты", () => {
    expect(shiftRange("2026-03-23", "2026-03-29", 1)).toEqual({ dateFrom: "2026-03-30", dateTo: "2026-04-05" });
  });
});

describe("rangeLabel", () => {
  it("в пределах месяца", () => {
    expect(rangeLabel("2026-11-23", "2026-11-29")).toBe("23–29 ноября");
  });

  it("через границу месяца и года", () => {
    expect(rangeLabel("2026-11-30", "2026-12-06")).toBe("30 ноября – 6 декабря");
    expect(rangeLabel("2026-12-28", "2027-01-03")).toBe("28 декабря 2026 – 3 января 2027");
  });

  it("один день", () => {
    expect(rangeLabel("2026-11-20", "2026-11-20")).toBe("20 ноября");
  });
});
