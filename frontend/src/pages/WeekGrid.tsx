import { ChangeEvent, CSSProperties, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { enqueueSync, fetchConnections, fetchGrid } from "../api";
import type { GridCell, GridResponse, GridSettings, Source, SuggestedSlot } from "../types";

export function WeekGrid() {
  const [settings, setSettings] = useState(readSettings);
  const [grid, setGrid] = useState<GridResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [slotIndex, setSlotIndex] = useState(0);
  const syncedRange = useRef<string | null>(null);

  useEffect(() => {
    writeSettings(settings);
  }, [settings]);

  useEffect(() => {
    let cancelled = false;
    const rangeKey = `${settings.dateFrom}:${settings.dateTo}`;
    const shouldSync = syncedRange.current !== rangeKey;
    const loader = shouldSync ? loadRange(settings) : fetchGrid(settings);
    loader
      .then((payload) => {
        if (!cancelled) {
          syncedRange.current = rangeKey;
          setGrid(payload);
          setSlotIndex(0);
          setError(null);
        }
      })
      .catch((reason: Error) => {
        if (!cancelled) {
          setError(reason.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [settings]);

  const cellsByKey = useMemo(() => indexCells(grid?.cells ?? []), [grid]);
  const timeKeys = useMemo(() => uniqueClocks(grid?.cells ?? []), [grid]);
  const days = useMemo(() => uniqueDays(grid?.cells ?? []), [grid]);
  const slots = grid?.slots ?? [];
  const activeSlotIndex = slots.length === 0 ? 0 : Math.min(slotIndex, slots.length - 1);

  return (
    <div className="page">
      <div className="card">
        <div className="layout">
          <section>
            <p className="eyebrow">СЕТКА</p>
            <GridControls settings={settings} onChange={setSettings} />
            {error ? <p className="error">{error}</p> : null}
            <div className="grid-wrap">
              <div className="week-grid" style={gridTemplateStyle(days.length, settings.stepMinutes)}>
                <div />
                {days.map((day) => (
                  <div key={day.index} className="day-head">
                    <span className="day-head-name">{day.weekday}</span>
                    <span className="day-head-date">{day.label}</span>
                  </div>
                ))}
                {timeKeys.map((clock) =>
                  renderTimeRow(clock, days, cellsByKey, slots, activeSlotIndex, settings.stepMinutes),
                )}
              </div>
            </div>
            <SlotSwitcher slots={slots} index={activeSlotIndex} onChange={setSlotIndex} />
            <p className="grid-hint">Красный — доля занятых. Тёмно-зелёный — выбранный слот, бледный — остальные варианты.</p>
          </section>
          <aside className="sidebar">
            <p className="eyebrow">КАЛЕНДАРИ</p>
            {loading && !grid ? <p className="muted">Загрузка…</p> : null}
            <SourceList sources={grid?.sources ?? []} />
            <div className="sidebar-actions">
              <Link className="primary-link" to="/connect">
                Подключить календарь
              </Link>
              <button
                type="button"
                className="text-btn"
                onClick={() => refreshAll(settings, setGrid, setSlotIndex, setError, setLoading)}
              >
                Обновить
              </button>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

function GridControls({
  settings,
  onChange,
}: {
  settings: GridSettings;
  onChange: (value: GridSettings) => void;
}) {
  function onFieldChange(event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) {
    applyControl(event, settings, onChange);
  }
  return (
    <form className="grid-controls" onSubmit={preventSubmit}>
      <label className="control">
        Детализация
        <select name="stepMinutes" value={settings.stepMinutes} onChange={onFieldChange}>
          {Constants.STEP_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label className="control">
        Длительность слота
        <select name="slotMinutes" value={settings.slotMinutes} onChange={onFieldChange}>
          {slotDurationOptions(settings.stepMinutes).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label className="control">
        Даты
        <span className="control-pair">
          <input name="dateFrom" type="date" value={settings.dateFrom} onChange={onFieldChange} />
          <span className="control-dash">—</span>
          <input name="dateTo" type="date" value={settings.dateTo} onChange={onFieldChange} />
        </span>
      </label>
      <label className="control">
        Время
        <span className="control-pair">
          <input
            name="timeFrom"
            type="time"
            step={Constants.TIME_INPUT_STEP}
            value={settings.timeFrom}
            onChange={onFieldChange}
          />
          <span className="control-dash">—</span>
          <input
            name="timeTo"
            type="time"
            step={Constants.TIME_INPUT_STEP}
            value={settings.timeTo}
            onChange={onFieldChange}
          />
        </span>
      </label>
    </form>
  );
}

function slotDurationOptions(stepMinutes: number) {
  return Constants.SLOT_OPTIONS.filter((option) => option.value >= stepMinutes && option.value % stepMinutes === 0);
}

function alignSlotMinutes(stepMinutes: number, slotMinutes: number): number {
  const options = slotDurationOptions(stepMinutes).map((option) => option.value);
  if (options.includes(slotMinutes)) {
    return slotMinutes;
  }
  const next = options.find((value) => value >= slotMinutes);
  return next ?? options[options.length - 1] ?? stepMinutes;
}

function SlotSwitcher({
  slots,
  index,
  onChange,
}: {
  slots: SuggestedSlot[];
  index: number;
  onChange: (value: number) => void;
}) {
  if (slots.length === 0) {
    return <p className="muted">Нет общего свободного слота такой длительности</p>;
  }
  function onPrev() {
    onChange(Math.max(0, index - 1));
  }
  function onNext() {
    onChange(Math.min(slots.length - 1, index + 1));
  }
  return (
    <div className="slot-switcher">
      <button type="button" className="nav-btn" disabled={index <= 0} onClick={onPrev}>
        ‹
      </button>
      <span className="slot-switcher-label">
        {index + 1} из {slots.length}: {formatSlotLabel(slots[index])}
      </span>
      <button type="button" className="nav-btn" disabled={index >= slots.length - 1} onClick={onNext}>
        ›
      </button>
    </div>
  );
}

function preventSubmit(event: FormEvent) {
  event.preventDefault();
}

function applyControl(
  event: ChangeEvent<HTMLInputElement | HTMLSelectElement>,
  settings: GridSettings,
  onChange: (value: GridSettings) => void,
) {
  onChange(nextSettings(settings, event.target.name, event.target.value));
}

function nextSettings(settings: GridSettings, name: string, raw: string): GridSettings {
  const next = { ...settings };
  if (name === "stepMinutes") {
    next.stepMinutes = Number(raw);
    next.slotMinutes = alignSlotMinutes(next.stepMinutes, next.slotMinutes);
  }
  if (name === "slotMinutes") {
    next.slotMinutes = alignSlotMinutes(next.stepMinutes, Number(raw));
  }
  if (name === "dateFrom") {
    next.dateFrom = raw;
  }
  if (name === "dateTo") {
    next.dateTo = raw;
  }
  if (name === "timeFrom") {
    next.timeFrom = raw;
  }
  if (name === "timeTo") {
    next.timeTo = raw;
  }
  return clampDates(next);
}

function clampDates(settings: GridSettings): GridSettings {
  const next = { ...settings };
  if (next.dateFrom > next.dateTo) {
    next.dateTo = next.dateFrom;
  }
  const from = parseIsoDate(next.dateFrom);
  const to = parseIsoDate(next.dateTo);
  const limit = new Date(from);
  limit.setDate(limit.getDate() + Constants.MAX_RANGE_DAYS - 1);
  if (to > limit) {
    next.dateTo = isoDate(limit);
  }
  return next;
}

function renderTimeRow(
  clock: string,
  days: DayHeader[],
  cellsByKey: Map<string, GridCell>,
  slots: SuggestedSlot[],
  activeSlotIndex: number,
  stepMinutes: number,
) {
  return (
    <div key={clock} className="contents-row">
      <div className="hour-label" style={rowItemStyle(stepMinutes)}>
        {formatClockLabel(clock, stepMinutes)}
      </div>
      {days.map((day) => {
        const cell = cellsByKey.get(cellKey(day.index, clock));
        return renderCell(day.index, clock, cell, slots, activeSlotIndex, stepMinutes);
      })}
    </div>
  );
}

function renderCell(
  dayIndex: number,
  clock: string,
  cell: GridCell | undefined,
  slots: SuggestedSlot[],
  activeSlotIndex: number,
  stepMinutes: number,
) {
  return (
    <div
      key={`${dayIndex}-${clock}`}
      className={cellClass(cell, slots, activeSlotIndex)}
      style={cellFillStyle(cell, slots, activeSlotIndex, stepMinutes)}
    >
      {cell ? <span className="cell-tip">{tooltipText(cell)}</span> : null}
    </div>
  );
}

function cellClass(cell: GridCell | undefined, slots: SuggestedSlot[], activeSlotIndex: number): string {
  const kind = slotKind(cell, slots, activeSlotIndex);
  if (kind === "active") {
    return "cell in-slot";
  }
  if (kind === "alt") {
    return "cell in-slot-alt";
  }
  return "cell";
}

function SourceList({ sources }: { sources: Source[] }) {
  if (sources.length === 0) {
    return (
      <p className="muted empty-note">
        Подключите Google, Яндекс или Apple — на сетке появятся свободные часы
      </p>
    );
  }
  return (
    <ul className="source-list">
      {sources.map((source) => (
        <li key={source.id} className="source-item">
          <span className={`status-mark status-${source.status}`} />
          <span>
            <span className="source-name">{source.name}</span>
            <span className="source-meta">
              {providerLabel(source.provider)} · {Constants.STATUS_LABELS[source.status] ?? source.status}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function loadRange(settings: GridSettings): Promise<GridResponse> {
  return fetchConnections().then((connections) => {
    if (connections.length === 0) {
      return fetchGrid(settings);
    }
    const jobs = connections.map((item) =>
      enqueueSync(item.id, settings.dateFrom, settings.dateTo).catch(() => undefined),
    );
    return Promise.all(jobs).then(() => delay(400).then(() => waitForGrid(settings)));
  });
}

function waitForGrid(settings: GridSettings): Promise<GridResponse> {
  return pollGrid(settings, 0);
}

function pollGrid(settings: GridSettings, attempt: number): Promise<GridResponse> {
  return fetchGrid(settings).then((payload) => {
    const syncing = payload.sources.some((item) => item.status === "syncing");
    if (!syncing || attempt >= 8) {
      return payload;
    }
    return delay(500).then(() => pollGrid(settings, attempt + 1));
  });
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function refreshAll(
  settings: GridSettings,
  setGrid: (value: GridResponse) => void,
  setSlotIndex: (value: number) => void,
  setError: (value: string | null) => void,
  setLoading: (value: boolean) => void,
) {
  setLoading(true);
  loadRange(settings)
    .then((payload) => {
      setGrid(payload);
      setSlotIndex(0);
      setError(null);
    })
    .catch((reason: Error) => setError(reason.message))
    .finally(() => setLoading(false));
}

function isoDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseIsoDate(value: string): Date {
  return new Date(`${value}T00:00:00`);
}

function indexCells(cells: GridCell[]): Map<string, GridCell> {
  const map = new Map<string, GridCell>();
  cells.forEach((cell) => {
    map.set(cellKey(cell.day_index, cellClock(cell)), cell);
  });
  return map;
}

function uniqueClocks(cells: GridCell[]): string[] {
  const seen = new Set<string>();
  const clocks: string[] = [];
  cells.forEach((cell) => {
    const clock = cellClock(cell);
    if (!seen.has(clock)) {
      seen.add(clock);
      clocks.push(clock);
    }
  });
  return clocks;
}

type DayHeader = {
  index: number;
  weekday: string;
  label: string;
};

function uniqueDays(cells: GridCell[]): DayHeader[] {
  const seen = new Set<number>();
  const days: DayHeader[] = [];
  cells.forEach((cell) => {
    if (seen.has(cell.day_index)) {
      return;
    }
    seen.add(cell.day_index);
    days.push(dayHeader(cell));
  });
  return days;
}

function dayHeader(cell: GridCell): DayHeader {
  const parts = cell.day.split("-");
  return {
    index: cell.day_index,
    weekday: Constants.DAY_LABELS[weekdayIndex(cell.day)],
    label: `${Number(parts[2])}.${Number(parts[1])}`,
  };
}

function weekdayIndex(isoDay: string): number {
  const jsDay = new Date(`${isoDay}T12:00:00`).getDay();
  return (jsDay + 6) % 7;
}

function cellClock(cell: GridCell): string {
  return formatClock(cell.hour, cell.minute);
}

function formatClock(hour: number, minute: number): string {
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

function cellKey(dayIndex: number, clock: string): string {
  return `${dayIndex}-${clock}`;
}

function formatClockLabel(clock: string, stepMinutes: number): string {
  const minute = Number(clock.slice(3, 5));
  if (minute === 0) {
    return `${Number(clock.slice(0, 2))}:00`;
  }
  if (stepMinutes >= Constants.LABEL_STEP_MINUTES) {
    return clock;
  }
  return "";
}

function tooltipText(cell: GridCell): string {
  const from = cellClock(cell);
  const duration = Math.round((Date.parse(cell.end) - Date.parse(cell.start)) / Constants.MS_IN_MINUTE);
  const until = shiftClock(from, duration);
  const busy = cell.total - cell.free_count;
  return `${from}–${until}\nСвободны: ${cell.free_count} из ${cell.total}\nЗаняты: ${busy}`;
}

function providerLabel(provider: string): string {
  if (provider === "google") {
    return "Google";
  }
  if (provider === "yandex") {
    return "Яндекс";
  }
  return "Apple";
}

function shiftClock(clock: string, deltaMinutes: number): string {
  const hour = Number(clock.slice(0, 2));
  const minute = Number(clock.slice(3, 5));
  const total = hour * Constants.MINUTES_IN_HOUR + minute + deltaMinutes;
  const wrapped = (total + Constants.MINUTES_IN_DAY) % Constants.MINUTES_IN_DAY;
  const nextHour = Math.floor(wrapped / Constants.MINUTES_IN_HOUR);
  const nextMinute = wrapped % Constants.MINUTES_IN_HOUR;
  return formatClock(nextHour, nextMinute);
}

function gridTemplateStyle(dayCount: number, stepMinutes: number): CSSProperties {
  const columns = Math.max(dayCount, 1);
  const height = rowHeight(stepMinutes);
  return {
    gridTemplateColumns: `52px repeat(${columns}, 1fr)`,
    gridTemplateRows: "auto",
    gridAutoRows: `${height}px`,
  };
}

function rowHeight(stepMinutes: number): number {
  return Math.max(
    Constants.CELL_MIN_HEIGHT,
    Math.round((stepMinutes / Constants.DEFAULT_STEP_MINUTES) * Constants.HOUR_CELL_HEIGHT),
  );
}

function rowItemStyle(stepMinutes: number): CSSProperties {
  const height = rowHeight(stepMinutes);
  return { height, minHeight: 0 };
}

function cellFillStyle(
  cell: GridCell | undefined,
  slots: SuggestedSlot[],
  activeSlotIndex: number,
  stepMinutes: number,
): CSSProperties {
  const busyRatio = cell && cell.total > 0 ? (cell.total - cell.free_count) / cell.total : 0;
  const busyAlpha = busyRatio * Constants.BUSY_MAX_ALPHA;
  const layers = [`linear-gradient(rgba(${Constants.BUSY_RGB}, ${busyAlpha}), rgba(${Constants.BUSY_RGB}, ${busyAlpha}))`];
  const kind = slotKind(cell, slots, activeSlotIndex);
  if (kind === "active") {
    layers.unshift(
      `linear-gradient(rgba(${Constants.SLOT_RGB}, ${Constants.SLOT_ALPHA}), rgba(${Constants.SLOT_RGB}, ${Constants.SLOT_ALPHA}))`,
    );
  }
  if (kind === "alt") {
    layers.unshift(
      `linear-gradient(rgba(${Constants.SLOT_RGB}, ${Constants.SLOT_ALT_ALPHA}), rgba(${Constants.SLOT_RGB}, ${Constants.SLOT_ALT_ALPHA}))`,
    );
  }
  return {
    ...rowItemStyle(stepMinutes),
    backgroundColor: Constants.CELL_BASE,
    backgroundImage: layers.join(", "),
  };
}

function slotKind(cell: GridCell | undefined, slots: SuggestedSlot[], activeSlotIndex: number): "active" | "alt" | null {
  if (!cell) {
    return null;
  }
  const active = slots[activeSlotIndex];
  if (active && cellInSlot(cell, active)) {
    return "active";
  }
  if (slots.some((slot, index) => index !== activeSlotIndex && cellInSlot(cell, slot))) {
    return "alt";
  }
  return null;
}

function cellInSlot(cell: GridCell, slot: SuggestedSlot): boolean {
  return Date.parse(cell.start) >= Date.parse(slot.start) && Date.parse(cell.end) <= Date.parse(slot.end);
}

function formatSlotLabel(slot: SuggestedSlot): string {
  const day = moscowDate(slot.start);
  const parts = day.split("-");
  return `${Constants.DAY_LABELS[weekdayIndex(day)]} ${Number(parts[2])}.${Number(parts[1])}, ${moscowClock(slot.start)}–${moscowClock(slot.end)}`;
}

function moscowDate(iso: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Moscow",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(iso));
}

function moscowClock(iso: string): string {
  const parts = new Intl.DateTimeFormat("ru-RU", {
    timeZone: "Europe/Moscow",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(new Date(iso));
  const hour = parts.find((part) => part.type === "hour")?.value ?? "00";
  const minute = parts.find((part) => part.type === "minute")?.value ?? "00";
  return `${hour}:${minute}`;
}

function defaultSettings(): GridSettings {
  const from = new Date();
  const to = new Date();
  to.setDate(from.getDate() + Constants.DEFAULT_RANGE_DAYS - 1);
  return {
    stepMinutes: 60,
    slotMinutes: 60,
    dateFrom: isoDate(from),
    dateTo: isoDate(to),
    timeFrom: "09:00",
    timeTo: "21:00",
  };
}

function readSettings(): GridSettings {
  const fallback = defaultSettings();
  try {
    const raw = window.localStorage.getItem(Constants.SETTINGS_KEY);
    if (!raw) {
      return fallback;
    }
    const parsed = JSON.parse(raw) as Partial<GridSettings>;
    return clampDates({
      stepMinutes: parsed.stepMinutes ?? fallback.stepMinutes,
      slotMinutes: alignSlotMinutes(parsed.stepMinutes ?? fallback.stepMinutes, parsed.slotMinutes ?? fallback.slotMinutes),
      dateFrom: parsed.dateFrom ?? fallback.dateFrom,
      dateTo: parsed.dateTo ?? fallback.dateTo,
      timeFrom: parsed.timeFrom ?? fallback.timeFrom,
      timeTo: parsed.timeTo ?? fallback.timeTo,
    });
  } catch {
    return fallback;
  }
}

function writeSettings(settings: GridSettings) {
  window.localStorage.setItem(Constants.SETTINGS_KEY, JSON.stringify(settings));
}

class Constants {
  static readonly DAY_LABELS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
  static readonly STATUS_LABELS: Record<string, string> = {
    active: "ок",
    pending: "ожидает",
    syncing: "обновляется",
    auth_failed: "ошибка входа",
  };
  static readonly STEP_OPTIONS = [
    { value: 15, label: "15 минут" },
    { value: 30, label: "30 минут" },
    { value: 45, label: "45 минут" },
    { value: 60, label: "1 час" },
    { value: 90, label: "1,5 часа" },
    { value: 120, label: "2 часа" },
  ];
  static readonly SLOT_OPTIONS = [
    { value: 15, label: "15 минут" },
    { value: 30, label: "30 минут" },
    { value: 45, label: "45 минут" },
    { value: 60, label: "1 час" },
    { value: 90, label: "1,5 часа" },
    { value: 120, label: "2 часа" },
    { value: 180, label: "3 часа" },
  ];
  static readonly SETTINGS_KEY = "slot-grid-settings";
  static readonly TIME_INPUT_STEP = 900;
  static readonly LABEL_STEP_MINUTES = 45;
  static readonly MINUTES_IN_HOUR = 60;
  static readonly MINUTES_IN_DAY = 1440;
  static readonly DEFAULT_STEP_MINUTES = 60;
  static readonly DEFAULT_RANGE_DAYS = 7;
  static readonly MAX_RANGE_DAYS = 14;
  static readonly HOUR_CELL_HEIGHT = 32;
  static readonly CELL_MIN_HEIGHT = 10;
  static readonly MS_IN_MINUTE = 60000;
  static readonly BUSY_RGB = "226, 56, 56";
  static readonly SLOT_RGB = "21, 92, 45";
  static readonly BUSY_MAX_ALPHA = 0.6;
  static readonly SLOT_ALPHA = 0.55;
  static readonly SLOT_ALT_ALPHA = 0.18;
  static readonly CELL_BASE = "#f7f7f7";
}
