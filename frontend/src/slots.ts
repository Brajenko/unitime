import type { GridCell } from "./types";

/**
 * Слот, который встанет при наведении на клетку `hovered`.
 * Сначала пробуем начать слот в самой клетке, иначе сдвигаем начало назад
 * к ближайшему допустимому так, чтобы слот покрывал эту клетку.
 * Возвращает индексы клеток слота или пустой массив, если слот не встаёт.
 */
export function slotPreview(cells: GridCell[], hovered: number, length: number): number[] {
  if (hovered < 0 || hovered >= cells.length || length < 1) {
    return [];
  }
  for (let start = hovered; start > hovered - length && start >= 0; start -= 1) {
    if (cells[start].slot_start) {
      return Array.from({ length }, (_, offset) => start + offset);
    }
  }
  return [];
}
