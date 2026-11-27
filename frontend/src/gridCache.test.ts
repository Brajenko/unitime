import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cacheKey, clearGridCache, loadCachedGrid, saveCachedGrid } from "./gridCache";
import type { GridResponse, GridSettings } from "./types";

const settings: GridSettings = {
  stepMinutes: 60,
  slotMinutes: 60,
  dateFrom: "2026-12-01",
  dateTo: "2026-12-07",
  timeFrom: "09:00",
  timeTo: "21:00",
};

function grid(): GridResponse {
  return {
    date_from: "2026-12-01",
    date_to: "2026-12-07",
    total: 1,
    cells: [],
    slot_minutes: 60,
    step_minutes: 60,
    sources: [],
    members: [],
    team_id: null,
    generated_at: "2026-12-01T10:00:00Z",
    tz: "Europe/Moscow",
  };
}

function fakeStorage() {
  const data = new Map<string, string>();
  return {
    get length() {
      return data.size;
    },
    key: (index: number) => [...data.keys()][index] ?? null,
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    removeItem: (key: string) => void data.delete(key),
  };
}

describe("gridCache", () => {
  beforeEach(() => {
    vi.stubGlobal("window", { localStorage: fakeStorage() });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("возвращает сетку только для того же ключа и пользователя", () => {
    const key = cacheKey("team-1", settings, "Europe/Moscow");
    saveCachedGrid("u1", key, grid());
    expect(loadCachedGrid("u1", key)?.generated_at).toBe("2026-12-01T10:00:00Z");
    expect(loadCachedGrid("u2", key)).toBeNull();
    expect(loadCachedGrid("u1", cacheKey("team-2", settings, "Europe/Moscow"))).toBeNull();
    expect(loadCachedGrid("u1", cacheKey("team-1", settings, "Asia/Yekaterinburg"))).toBeNull();
  });

  it("битый json не ломает загрузку", () => {
    window.localStorage.setItem("slot-grid-cache:u1", "{oops");
    expect(loadCachedGrid("u1", "k")).toBeNull();
  });

  it("clearGridCache стирает кеш всех пользователей и не трогает чужие ключи", () => {
    saveCachedGrid("u1", "k", grid());
    saveCachedGrid("u2", "k", grid());
    window.localStorage.setItem("slot-team-id", "t");
    clearGridCache();
    expect(loadCachedGrid("u1", "k")).toBeNull();
    expect(loadCachedGrid("u2", "k")).toBeNull();
    expect(window.localStorage.getItem("slot-team-id")).toBe("t");
  });

  it("недоступное хранилище не бросает исключений", () => {
    vi.stubGlobal("window", {
      get localStorage(): Storage {
        throw new Error("blocked");
      },
    });
    expect(() => saveCachedGrid("u1", "k", grid())).not.toThrow();
    expect(loadCachedGrid("u1", "k")).toBeNull();
    expect(() => clearGridCache()).not.toThrow();
  });
});
