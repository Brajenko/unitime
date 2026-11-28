import type { GridResponse, GridSettings } from "./types";

const PREFIX = "slot-grid-cache:";

type Stored = { key: string; grid: GridResponse };

/** Последняя сетка пользователя: открываем страницу мгновенно, пока идёт обновление. */
export function cacheKey(teamId: string | null, settings: GridSettings, tz: string): string {
  return JSON.stringify([teamId, settings, tz]);
}

export function loadCachedGrid(userId: string, key: string): GridResponse | null {
  try {
    const raw = window.localStorage.getItem(PREFIX + userId);
    if (!raw) {
      return null;
    }
    const stored = JSON.parse(raw) as Stored;
    return stored.key === key && stored.grid && Array.isArray(stored.grid.cells) ? stored.grid : null;
  } catch {
    return null;
  }
}

export function saveCachedGrid(userId: string, key: string, grid: GridResponse): void {
  try {
    window.localStorage.setItem(PREFIX + userId, JSON.stringify({ key, grid } satisfies Stored));
  } catch {
    // хранилище недоступно или переполнено — просто без кеша
  }
}

/** На выходе кеш стираем: в нём почты команды и занятость. */
export function clearGridCache(): void {
  try {
    const keys: string[] = [];
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index);
      if (key?.startsWith(PREFIX)) {
        keys.push(key);
      }
    }
    keys.forEach((key) => window.localStorage.removeItem(key));
  } catch {
    // нечего чистить
  }
}
