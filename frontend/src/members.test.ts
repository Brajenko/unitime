import { describe, expect, it } from "vitest";
import { agoLabel, memberMark, memberNote, memberSummary, missingNames, sortMembers } from "./members";
import type { GridMember, MemberStatus } from "./types";

const NOW = Date.parse("2026-12-01T12:00:00Z");

function member(email: string, status: MemberStatus, extra: Partial<GridMember> = {}): GridMember {
  return {
    user_id: email,
    email,
    calendars: status === "no_calendars" || status === "auth_failed" ? 0 : 1,
    last_synced_at: "2026-12-01T11:55:00Z",
    in_overlay: status === "ok" || status === "stale" || status === "manual",
    status,
    ...extra,
  };
}

describe("memberSummary", () => {
  it("считает учтённых и собирает отсутствующих", () => {
    const summary = memberSummary([
      member("a@x", "ok"),
      member("b@x", "no_calendars"),
      member("c@x", "auth_failed"),
      member("d@x", "stale"),
    ]);
    expect(summary.total).toBe(4);
    expect(summary.counted).toBe(2);
    expect(summary.missing.map((item) => item.email)).toEqual(["b@x", "c@x"]);
    expect(summary.stale.map((item) => item.email)).toEqual(["d@x"]);
    expect(missingNames(summary)).toBe("b@x, c@x");
  });

  it("все подключены — отсутствующих нет", () => {
    const summary = memberSummary([member("a@x", "ok"), member("b@x", "ok")]);
    expect(summary).toMatchObject({ counted: 2, total: 2, missing: [], stale: [] });
  });

  it("пустой список не падает", () => {
    expect(memberSummary([])).toEqual({ counted: 0, total: 0, missing: [], stale: [] });
  });
});

describe("sortMembers", () => {
  it("проблемные наверху, порядок внутри групп сохраняется", () => {
    const sorted = sortMembers([member("a@x", "ok"), member("b@x", "no_calendars"), member("c@x", "ok"), member("d@x", "stale")]);
    expect(sorted.map((item) => item.email)).toEqual(["b@x", "d@x", "a@x", "c@x"]);
  });
});

describe("memberNote и memberMark", () => {
  it("подписи по статусам", () => {
    expect(memberNote(member("a@x", "no_calendars"), NOW)).toBe("не подключил календарь");
    expect(memberNote(member("a@x", "auth_failed"), NOW)).toContain("переподключить");
    expect(memberNote(member("a@x", "ok"), NOW)).toBe("1 календ. · обновлено 5 мин назад");
    expect(memberNote(member("a@x", "stale", { last_synced_at: "2026-12-01T09:00:00Z" }), NOW)).toBe(
      "1 календ. · данные устарели, обновлено 3 ч назад",
    );
    expect(memberNote(member("a@x", "stale", { last_synced_at: null }), NOW)).toBe("1 календ. · ещё не обновлялось");
  });

  it("метки статусов", () => {
    expect(memberMark(member("a@x", "ok"))).toBe("status-active");
    expect(memberMark(member("a@x", "stale"))).toBe("status-syncing");
    expect(memberMark(member("a@x", "no_calendars"))).toBe("status-pending");
    expect(memberMark(member("a@x", "auth_failed"))).toBe("status-auth_failed");
  });
});

describe("ручной режим", () => {
  it("manual учтён, не проблемный и подписан", () => {
    const manual = member("m@x", "manual", { calendars: 0, last_synced_at: null });
    const summary = memberSummary([manual, member("b@x", "no_calendars")]);
    expect(summary.counted).toBe(1);
    expect(summary.missing.map((item) => item.email)).toEqual(["b@x"]);
    expect(memberNote(manual, NOW)).toBe("отметил окна вручную");
    expect(memberMark(manual)).toBe("status-active");
    expect(sortMembers([manual, member("b@x", "no_calendars")]).map((item) => item.email)).toEqual(["b@x", "m@x"]);
  });
});

describe("agoLabel", () => {
  it("минуты, часы, дни", () => {
    expect(agoLabel("2026-12-01T12:00:00Z", NOW)).toBe("только что");
    expect(agoLabel("2026-11-30T12:00:00Z", NOW)).toBe("1 дн назад");
    expect(agoLabel("2026-12-01T12:30:00Z", NOW)).toBe("только что");
  });
});
