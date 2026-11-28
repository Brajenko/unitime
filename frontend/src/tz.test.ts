import { describe, expect, it } from "vitest";
import { clockIn, dayLabelIn } from "./tz";

describe("tz", () => {
  it("показывает одно и то же время в разных поясах", () => {
    expect(clockIn("2026-12-01T07:00:00Z", "Europe/Moscow")).toBe("10:00");
    expect(clockIn("2026-12-01T07:00:00Z", "Asia/Yekaterinburg")).toBe("12:00");
  });

  it("полночь выводится как 00:00", () => {
    expect(clockIn("2026-12-01T21:00:00Z", "Europe/Moscow")).toBe("00:00");
  });

  it("день недели и дата считаются в заданном поясе", () => {
    expect(dayLabelIn("2026-12-03T10:00:00Z", "Europe/Moscow")).toBe("Чт 3.12");
    // 22:00 UTC уже следующий день в Екатеринбурге
    expect(dayLabelIn("2026-12-03T22:00:00Z", "Asia/Yekaterinburg")).toBe("Пт 4.12");
  });
});
