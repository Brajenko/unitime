import { ChangeEvent, CSSProperties, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  cancelMeeting,
  createMeeting,
  deleteConnection,
  enqueueSync,
  fetchAvailability,
  fetchConnections,
  fetchGrid,
  fetchMeetings,
  fetchSyncJob,
  fetchTeams,
  logout,
  saveAvailability,
  UnauthorizedError,
} from "../api";
import { paintRect, windowsForSave, windowsToCellSet } from "../availability";
import { cacheKey, clearGridCache, loadCachedGrid, saveCachedGrid } from "../gridCache";
import { memberSummary, missingNames } from "../members";
import { meetingCellKeys } from "../meetings";
import { slotPreview } from "../slots";
import { BROWSER_TZ, clockIn } from "../tz";
import type { AvailabilityWindow, GridCell, GridMember, GridResponse, GridSettings, Meeting, Source, Team, User } from "../types";
import { rangeLabel, shiftRange } from "../range";
import { TeamPanel } from "./TeamPanel";
import { TopBar } from "./TopBar";

export function WeekGrid({ user, onLogout, teamKey }: { user: User; onLogout: () => void; teamKey: string }) {
  const [settings, setSettings] = useState(readSettings);
  const [teams, setTeams] = useState<Team[]>([]);
  const [teamId, setTeamId] = useState<string | null>(() => readStored(teamKey));
  const [grid, setGrid] = useState<GridResponse | null>(() =>
    loadCachedGrid(user.id, cacheKey(readStored(teamKey), readSettings(), BROWSER_TZ)),
  );
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [hovered, setHovered] = useState<number | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [meetingsTick, setMeetingsTick] = useState(0);
  const [meetingError, setMeetingError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [marking, setMarking] = useState(false);
  const [myFree, setMyFree] = useState<Set<number>>(() => new Set());
  const [myOriginal, setMyOriginal] = useState<AvailabilityWindow[]>([]);
  const [markBusy, setMarkBusy] = useState(false);
  const [markError, setMarkError] = useState<string | null>(null);
  const paint = useRef<{ anchor: number; value: boolean; snapshot: Set<number> } | null>(null);
  const syncedRange = useRef<string | null>(null);
  const gridKey = cacheKey(teamId, settings, BROWSER_TZ);
  const applyGrid = useCallback(
    (payload: GridResponse) => {
      setGrid(payload);
      saveCachedGrid(user.id, gridKey, payload);
    },
    [user.id, gridKey],
  );
  const leave = useCallback(() => {
    clearGridCache();
    onLogout();
  }, [onLogout]);

  useEffect(() => {
    writeSettings(settings);
  }, [settings]);

  useEffect(() => {
    fetchTeams()
      .then((items) => {
        setTeams(items);
        setTeamId((current) => (current && items.some((item) => item.id === current) ? current : null));
      })
      .catch(() => setTeams([]));
  }, []);

  useEffect(() => {
    try {
      if (teamId) {
        window.localStorage.setItem(teamKey, teamId);
      } else {
        window.localStorage.removeItem(teamKey);
      }
    } catch {
      // без хранилища выбор команды не запоминается
    }
  }, [teamId, teamKey]);

  useEffect(() => {
    let cancelled = false;
    const cached = loadCachedGrid(user.id, gridKey);
    if (cached) {
      setGrid(cached);
    }
    setLoading(true);
    const rangeKey = `${settings.dateFrom}:${settings.dateTo}`;
    const shouldSync = syncedRange.current !== rangeKey;
    const loader = shouldSync ? loadRange(settings, teamId) : fetchGrid(settings, teamId);
    loader
      .then((payload) => {
        if (!cancelled) {
          syncedRange.current = rangeKey;
          applyGrid(payload);
          setError(null);
        }
      })
      .catch((reason: Error) => {
        if (!cancelled) {
          setError(reason.message);
          if (reason instanceof UnauthorizedError) {
            leave();
          }
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
  }, [settings, teamId, user.id, gridKey, applyGrid, leave]);

  useEffect(() => {
    if (!teamId) {
      setMeetings([]);
      return undefined;
    }
    let cancelled = false;
    fetchMeetings(teamId)
      .then((items) => {
        if (!cancelled) {
          setMeetings(items);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setMeetings([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [teamId, meetingsTick]);

  useEffect(() => {
    // выделение и разметка привязаны к клеткам текущей сетки: при смене настроек сбрасываем
    setMarking(false);
    setSelected([]);
  }, [settings, teamId]);

  useEffect(() => {
    function stopPaint() {
      paint.current = null;
    }
    window.addEventListener("mouseup", stopPaint);
    return () => window.removeEventListener("mouseup", stopPaint);
  }, []);

  const cellsByKey = useMemo(() => indexCells(grid?.cells ?? []), [grid]);
  const timeKeys = useMemo(() => uniqueClocks(grid?.cells ?? []), [grid]);
  const days = useMemo(() => uniqueDays(grid?.cells ?? []), [grid]);
  const slotLength = grid ? Math.round(grid.slot_minutes / grid.step_minutes) : 1;
  const preview = useMemo(() => {
    if (!grid || marking) {
      return new Set<number>();
    }
    if (hovered !== null) {
      const hoveredSlot = slotPreview(grid.cells, hovered, slotLength);
      if (hoveredSlot.length > 0) {
        return new Set(hoveredSlot);
      }
    }
    return new Set(selected);
  }, [grid, hovered, selected, slotLength, marking]);
  const slotRange = useMemo(() => {
    if (!grid || preview.size === 0) {
      return null;
    }
    const indexes = Array.from(preview).sort((left, right) => left - right);
    return `${clockIn(grid.cells[indexes[0]].start, grid.tz)}–${clockIn(grid.cells[indexes[indexes.length - 1]].end, grid.tz)}`;
  }, [grid, preview]);
  const meetingCells = useMemo(() => meetingCellKeys(grid?.cells ?? [], meetings), [grid, meetings]);
  const summary = useMemo(() => memberSummary(grid?.members ?? []), [grid]);
  const team = teams.find((item) => item.id === teamId) ?? null;
  const me = grid?.members.find((member) => member.user_id === user.id) ?? null;

  function refresh() {
    refreshAll(settings, teamId, applyGrid, setError, setLoading);
    setMeetingsTick((value) => value + 1);
  }

  function startMarking() {
    if (!grid) {
      return;
    }
    setMarkBusy(true);
    setMarkError(null);
    setSelected([]);
    fetchAvailability(settings)
      .then((windows) => {
        setMyOriginal(windows);
        setMyFree(windowsToCellSet(grid.cells, windows));
        setMarking(true);
      })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setMarkBusy(false));
  }

  function paintCell(index: number, start: boolean) {
    if (!marking || !grid || index < 0) {
      return;
    }
    if (start) {
      paint.current = { anchor: index, value: !myFree.has(index), snapshot: new Set(myFree) };
    }
    const state = paint.current;
    if (!state) {
      return;
    }
    setMyFree(paintRect(grid.cells, state.snapshot, state.anchor, index, state.value));
  }

  function saveMarking() {
    if (!grid) {
      return;
    }
    const range = {
      start: new Date(`${settings.dateFrom}T00:00:00`).getTime(),
      end: new Date(`${settings.dateTo}T00:00:00`).getTime() + Constants.MS_IN_DAY,
    };
    setMarkBusy(true);
    setMarkError(null);
    saveAvailability(settings, windowsForSave(grid.cells, myOriginal, myFree, range))
      .then(() => fetchGrid(settings, teamId))
      .then((payload) => {
        applyGrid(payload);
        setMarking(false);
      })
      .catch((reason: Error) => setMarkError(reason.message))
      .finally(() => setMarkBusy(false));
  }

  function pickSlot(index: number) {
    if (marking || !grid || index < 0) {
      return;
    }
    const indexes = slotPreview(grid.cells, index, slotLength);
    setMeetingError(null);
    if (indexes.length === 0) {
      setSelected([]);
      return;
    }
    setSelected(indexes);
  }

  function fixMeeting(title: string) {
    if (!grid || !teamId || selected.length === 0) {
      return;
    }
    if (selected.some((item) => meetingCells.has(item))) {
      setMeetingError("Это время уже занято встречей");
      return;
    }
    const first = grid.cells[selected[0]];
    const last = grid.cells[selected[selected.length - 1]];
    setSaving(true);
    createMeeting(teamId, first.start, last.end, title)
      .then(() => {
        setSelected([]);
        setMeetingError(null);
        setMeetingsTick((value) => value + 1);
      })
      .catch((reason: Error) => setMeetingError(reason.message))
      .finally(() => setSaving(false));
  }

  function removeMeeting(meeting: Meeting) {
    if (!window.confirm("Отменить встречу?")) {
      return;
    }
    cancelMeeting(meeting.id)
      .then(() => setMeetingsTick((value) => value + 1))
      .catch((reason: Error) => setError(reason.message));
  }

  const cellIndex = useMemo(() => new Map((grid?.cells ?? []).map((cell, index) => [cell, index])), [grid]);
  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const hasSlots = (grid?.cells ?? []).some((cell) => cell.slot_start);
  const hasCalendar = (grid?.sources.length ?? 0) > 0;

  const rowContext: RowContext = {
    cellsByKey,
    cellIndex,
    preview,
    slotRange,
    meetingCells,
    canFix: !marking,
    marking,
    mine: myFree,
    selected: selectedSet,
    onHover: setHovered,
    onPick: pickSlot,
    onPaint: paintCell,
    stepMinutes: settings.stepMinutes,
  };

  return (
    <div className="page">
      <div className="card">
        <TopBar
          user={user}
          teams={teams}
          teamId={teamId}
          onSelect={setTeamId}
          onCreated={(created) => {
            setTeams((items) => [...items, created]);
            setTeamId(created.id);
          }}
          onLogout={() => logout().finally(leave)}
        />
        <div className="layout">
          <section>
            <GridToolbar
              settings={settings}
              onChange={setSettings}
              grid={grid}
              loading={loading}
              disabled={marking}
              onRefresh={refresh}
            />
            {error ? <p className="error">{error}</p> : null}
            {marking ? (
              <MarkBar
                busy={markBusy}
                hasCalendar={hasCalendar}
                count={myFree.size}
                error={markError}
                onSave={saveMarking}
                onClear={() => setMyFree(new Set())}
                onCancel={() => {
                  setMarking(false);
                  setMarkError(null);
                }}
              />
            ) : teamId && summary.missing.length > 0 ? (
              <p className="warning">
                Без учёта: {missingNames(summary)} — зелёные окна могут быть неверными
              </p>
            ) : null}
            <div className={marking ? "grid-wrap marking" : "grid-wrap"}>
              <div
                className="week-grid"
                style={gridTemplateStyle(days.length, settings.stepMinutes)}
                onMouseLeave={() => setHovered(null)}
              >
                <div />
                {days.map((day) => (
                  <div key={day.index} className="day-head">
                    <span className="day-head-name">{day.weekday}</span>
                    <span className="day-head-date">{day.label}</span>
                  </div>
                ))}
                {timeKeys.map((clock) => renderTimeRow(clock, days, rowContext))}
              </div>
            </div>
            {marking ? null : (
              <SlotCard
                grid={grid}
                selected={selected}
                hasSlots={hasSlots}
                team={team}
                saving={saving}
                error={meetingError}
                onFix={fixMeeting}
                onClose={() => {
                  setSelected([]);
                  setMeetingError(null);
                }}
              />
            )}
          </section>
          <aside className="sidebar">
            <MyAvailability
              sources={grid?.sources ?? []}
              me={me}
              loading={loading && !grid}
              marking={marking}
              busy={markBusy || !grid}
              onMark={startMarking}
              onRemove={(source) => removeSource(source, refresh, setError)}
            />
            <TeamPanel
              team={team}
              members={grid?.members ?? []}
              meetings={meetings}
              tz={grid?.tz ?? BROWSER_TZ}
              onCancelMeeting={removeMeeting}
            />
          </aside>
        </div>
      </div>
    </div>
  );
}

function GridToolbar({
  settings,
  onChange,
  grid,
  loading,
  disabled,
  onRefresh,
}: {
  settings: GridSettings;
  onChange: (value: GridSettings) => void;
  grid: GridResponse | null;
  loading: boolean;
  disabled: boolean;
  onRefresh: () => void;
}) {
  const [viewOpen, setViewOpen] = useState(false);
  function onFieldChange(event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) {
    applyControl(event, settings, onChange);
  }
  function shift(direction: 1 | -1) {
    onChange({ ...settings, ...shiftRange(settings.dateFrom, settings.dateTo, direction) });
  }
  return (
    <div className="toolbar">
      <div className="toolbar-row">
        <span className="week-nav">
          <button type="button" className="nav-btn" aria-label="Предыдущая неделя" disabled={disabled} onClick={() => shift(-1)}>
            ←
          </button>
          <span className="week-label">{rangeLabel(settings.dateFrom, settings.dateTo)}</span>
          <button type="button" className="nav-btn" aria-label="Следующая неделя" disabled={disabled} onClick={() => shift(1)}>
            →
          </button>
        </span>
        <label className="control control-inline">
          Встреча
          <select name="slotMinutes" value={settings.slotMinutes} disabled={disabled} onChange={onFieldChange}>
            {slotDurationOptions(settings.stepMinutes).map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="text-btn" onClick={() => setViewOpen((open) => !open)}>
          ⚙ Вид
        </button>
        <span className="toolbar-fresh">
          {grid ? `Данные от ${clockIn(grid.generated_at, grid.tz)}` : ""}
          {loading ? " · обновляется…" : ""}
          <button type="button" className="text-btn" onClick={onRefresh} disabled={loading}>
            ⟳ Обновить
          </button>
        </span>
      </div>
      {viewOpen ? (
        <form className="grid-controls" onSubmit={preventSubmit}>
          <label className="control">
            Детализация
            <select name="stepMinutes" value={settings.stepMinutes} disabled={disabled} onChange={onFieldChange}>
              {Constants.STEP_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="control">
            Даты
            <span className="control-pair">
              <input name="dateFrom" type="date" value={settings.dateFrom} disabled={disabled} onChange={onFieldChange} />
              <span className="control-dash">—</span>
              <input name="dateTo" type="date" value={settings.dateTo} disabled={disabled} onChange={onFieldChange} />
            </span>
          </label>
          <label className="control">
            Часы
            <span className="control-pair">
              <input
                name="timeFrom"
                type="time"
                step={Constants.TIME_INPUT_STEP}
                value={settings.timeFrom}
                disabled={disabled}
                onChange={onFieldChange}
              />
              <span className="control-dash">—</span>
              <input
                name="timeTo"
                type="time"
                step={Constants.TIME_INPUT_STEP}
                value={settings.timeTo}
                disabled={disabled}
                onChange={onFieldChange}
              />
            </span>
          </label>
        </form>
      ) : null}
    </div>
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

function SlotCard({
  grid,
  selected,
  hasSlots,
  team,
  saving,
  error,
  onFix,
  onClose,
}: {
  grid: GridResponse | null;
  selected: number[];
  hasSlots: boolean;
  team: Team | null;
  saving: boolean;
  error: string | null;
  onFix: (title: string) => void;
  onClose: () => void;
}) {
  const [title, setTitle] = useState("");
  if (!grid || grid.total === 0) {
    return null;
  }
  if (selected.length === 0) {
    return (
      <p className="muted slot-hint">
        {hasSlots ? "Нажмите на зелёную клетку, чтобы выбрать слот" : "Нет общего свободного слота такой длительности"}
      </p>
    );
  }
  const first = grid.cells[selected[0]];
  const last = grid.cells[selected[selected.length - 1]];
  return (
    <form
      className="slot-card"
      onSubmit={(event) => {
        event.preventDefault();
        onFix(title);
        setTitle("");
      }}
    >
      <div className="slot-card-head">
        <span className="slot-card-title">
          Выбран слот: {formatCellDay(first)}, {clockIn(first.start, grid.tz)}–{clockIn(last.end, grid.tz)}
        </span>
        <button type="button" className="source-remove" aria-label="Снять выбор" onClick={onClose}>
          ×
        </button>
      </div>
      <span className="muted">
        Свободны {first.free_count} из {first.total}
        {team ? "" : " · это только ваша занятость"}
      </span>
      {team ? (
        <span className="slot-card-actions">
          <input
            value={title}
            maxLength={200}
            placeholder="Название встречи (необязательно)"
            onChange={(event) => setTitle(event.target.value)}
          />
          <button type="submit" className="primary" disabled={saving}>
            {saving ? "Сохраняем…" : "Зафиксировать встречу"}
          </button>
        </span>
      ) : (
        <span className="muted">Чтобы назначить встречу, выберите команду вверху.</span>
      )}
      {error ? <p className="error">{error}</p> : null}
    </form>
  );
}

function formatCellDay(cell: GridCell): string {
  const parts = cell.day.split("-");
  return `${Constants.DAY_LABELS[weekdayIndex(cell.day)]} ${Number(parts[2])}.${Number(parts[1])}`;
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

type RowContext = {
  cellsByKey: Map<string, GridCell>;
  cellIndex: Map<GridCell, number>;
  preview: Set<number>;
  slotRange: string | null;
  meetingCells: Map<number, Meeting>;
  canFix: boolean;
  marking: boolean;
  mine: Set<number>;
  selected: Set<number>;
  onHover: (index: number | null) => void;
  onPick: (index: number) => void;
  onPaint: (index: number, start: boolean) => void;
  stepMinutes: number;
};

function MarkBar({
  busy,
  hasCalendar,
  count,
  error,
  onSave,
  onClear,
  onCancel,
}: {
  busy: boolean;
  hasCalendar: boolean;
  count: number;
  error: string | null;
  onSave: () => void;
  onClear: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="mark-bar">
      <p className="mark-hint">
        <strong>Мои свободные окна.</strong> Нажмите на клетку или выделите прямоугольник мышью. В днях, где отмечено
        хоть что-то, остальное время считается занятым; дни без отметок команда не учитывает.
      </p>
      {hasCalendar ? (
        <p className="warning">У вас подключён календарь — сетка считается по нему, ручные окна не учитываются.</p>
      ) : null}
      <span className="slot-card-actions">
        <button type="button" className="primary" disabled={busy} onClick={onSave}>
          {busy ? "Сохраняем…" : `Сохранить (${count})`}
        </button>
        <button type="button" className="text-btn" disabled={busy} onClick={onClear}>
          Очистить
        </button>
        <button type="button" className="text-btn" disabled={busy} onClick={onCancel}>
          Отмена
        </button>
      </span>
      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}

function MyAvailability({
  sources,
  me,
  loading,
  marking,
  busy,
  onMark,
  onRemove,
}: {
  sources: Source[];
  me: GridMember | null;
  loading: boolean;
  marking: boolean;
  busy: boolean;
  onMark: () => void;
  onRemove: (source: Source) => void;
}) {
  const manual = me?.status === "manual";
  const unknown = sources.length === 0 && !manual;
  return (
    <section className={unknown ? "panel-block panel-attention" : "panel-block"}>
      <p className="eyebrow">МОЯ ЗАНЯТОСТЬ</p>
      {loading ? <p className="muted">Загрузка…</p> : null}
      {sources.length > 0 ? <SourceList sources={sources} onRemove={onRemove} /> : null}
      {manual ? <p className="source-meta">Окна отмечены вручную</p> : null}
      {unknown && !loading ? (
        <p className="muted empty-note">
          Сервис пока не знает, когда вы свободны. Подключите календарь или отметьте окна вручную.
        </p>
      ) : null}
      <div className="panel-actions">
        <Link className="secondary" to="/connect">
          + Календарь
        </Link>
        <button type="button" className="secondary" disabled={busy || marking} onClick={onMark}>
          ✎ Окна вручную
        </button>
      </div>
      {sources.length > 0 ? <p className="source-meta">Календарь главнее ручных окон.</p> : null}
    </section>
  );
}

function renderTimeRow(clock: string, days: DayHeader[], context: RowContext) {
  return (
    <div key={clock} className="contents-row">
      <div className="hour-label" style={rowItemStyle(context.stepMinutes)}>
        {formatClockLabel(clock, context.stepMinutes)}
      </div>
      {days.map((day) => {
        const cell = context.cellsByKey.get(cellKey(day.index, clock));
        return renderCell(day.index, clock, cell, cell ? context.cellIndex.get(cell) ?? -1 : -1, context);
      })}
    </div>
  );
}

function renderCell(dayIndex: number, clock: string, cell: GridCell | undefined, index: number, context: RowContext) {
  const kind = context.marking ? null : slotKind(cell, index, context.preview);
  const meeting = context.marking ? undefined : context.meetingCells.get(index);
  const classes = ["cell"];
  if (kind === "active") {
    classes.push("in-slot");
    if (context.canFix) {
      classes.push("pickable");
    }
  } else if (kind === "alt") {
    classes.push("in-slot-alt");
  }
  if (meeting) {
    classes.push("meeting");
  }
  if (context.selected.has(index)) {
    classes.push("selected");
  }
  if (context.marking) {
    classes.push("markable");
    if (context.mine.has(index)) {
      classes.push("mine");
    }
  }
  return (
    <div
      key={`${dayIndex}-${clock}`}
      className={classes.join(" ")}
      style={
        context.marking
          ? { ...rowItemStyle(context.stepMinutes), backgroundColor: Constants.CELL_BASE }
          : cellFillStyle(cell, kind, context.stepMinutes, meeting !== undefined)
      }
      onMouseEnter={() => {
        context.onHover(index >= 0 ? index : null);
        context.onPaint(index, false);
      }}
      onMouseDown={(event) => {
        if (context.marking) {
          event.preventDefault();
          context.onPaint(index, true);
        }
      }}
      onClick={() => context.onPick(index)}
    >
      {cell && !context.marking ? (
        <span className="cell-tip">{tooltipText(cell, kind === "active" ? context.slotRange : null, meeting)}</span>
      ) : null}
    </div>
  );
}

function SourceList({ sources, onRemove }: { sources: Source[]; onRemove: (source: Source) => void }) {
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
          <span className="source-text" title={source.last_error ?? undefined}>
            <span className="source-name">{source.name}</span>
            <span className="source-meta">
              {providerLabel(source.provider)} · {statusLabel(source)}
            </span>
          </span>
          <button
            type="button"
            className="source-remove"
            title="Отключить подключение"
            aria-label={`Отключить: ${source.name}`}
            onClick={() => onRemove(source)}
          >
            ×
          </button>
        </li>
      ))}
    </ul>
  );
}

function statusLabel(source: Source): string {
  if (source.status === "auth_failed" && source.provider === "link") {
    return "ссылка недоступна";
  }
  return Constants.STATUS_LABELS[source.status] ?? source.status;
}

function removeSource(source: Source, reload: () => void, setError: (value: string | null) => void) {
  const what = source.provider === "link" ? "эту ссылку" : "подключение и все его календари";
  if (!window.confirm(`Отключить ${what}?`)) {
    return;
  }
  deleteConnection(source.connection_id)
    .then(reload)
    .catch((reason: Error) => setError(reason.message));
}

async function loadRange(settings: GridSettings, teamId: string | null): Promise<GridResponse> {
  const connections = await fetchConnections();
  const jobs = await Promise.all(connections.map(async (connection) => {
    const accepted = await enqueueSync(connection.id, settings.dateFrom, settings.dateTo).catch(() => undefined);
    return accepted && { connectionId: connection.id, jobId: accepted.job_id };
  }));
  const acceptedJobs = jobs.filter((job) => job !== undefined);
  for (let attempt = 0; attempt < 8 && acceptedJobs.length > 0; attempt++) {
    const states = await Promise.all(acceptedJobs.map(({ connectionId, jobId }) =>
      fetchSyncJob(connectionId, jobId).catch(() => undefined),
    ));
    if (!states.some((job) => job?.status === "queued" || job?.status === "running")) {
      break;
    }
    await delay(500);
  }
  return fetchGrid(settings, teamId);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function refreshAll(
  settings: GridSettings,
  teamId: string | null,
  setGrid: (value: GridResponse) => void,
  setError: (value: string | null) => void,
  setLoading: (value: boolean) => void,
) {
  setLoading(true);
  loadRange(settings, teamId)
    .then((payload) => {
      setGrid(payload);
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

function tooltipText(cell: GridCell, slotRange: string | null, meeting?: Meeting): string {
  const from = cellClock(cell);
  const duration = Math.round((Date.parse(cell.end) - Date.parse(cell.start)) / Constants.MS_IN_MINUTE);
  const until = shiftClock(from, duration);
  const busy = cell.total - cell.free_count;
  const title = slotRange ? `Слот ${slotRange}` : `${from}–${until}`;
  const base = `${title}\nСвободны: ${cell.free_count}/${cell.total}\nЗаняты: ${busy}`;
  return meeting ? `Встреча: ${meeting.title ?? "без названия"}\n${base}` : base;
}

function providerLabel(provider: string): string {
  if (provider === "google") {
    return "Google";
  }
  if (provider === "yandex") {
    return "Яндекс";
  }
  if (provider === "link") {
    return "Ссылка";
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
  kind: "active" | "alt" | null,
  stepMinutes: number,
  isMeeting: boolean,
): CSSProperties {
  const busyRatio = cell && cell.total > 0 ? (cell.total - cell.free_count) / cell.total : 0;
  const busyAlpha = busyRatio * Constants.BUSY_MAX_ALPHA;
  const layers = [`linear-gradient(rgba(${Constants.BUSY_RGB}, ${busyAlpha}), rgba(${Constants.BUSY_RGB}, ${busyAlpha}))`];
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
  if (isMeeting) {
    layers.unshift(
      `linear-gradient(rgba(${Constants.MEETING_RGB}, ${Constants.MEETING_ALPHA}), rgba(${Constants.MEETING_RGB}, ${Constants.MEETING_ALPHA}))`,
    );
  }
  return {
    ...rowItemStyle(stepMinutes),
    backgroundColor: Constants.CELL_BASE,
    backgroundImage: layers.join(", "),
  };
}

function slotKind(cell: GridCell | undefined, index: number, preview: Set<number>): "active" | "alt" | null {
  if (!cell) {
    return null;
  }
  if (preview.has(index)) {
    return "active";
  }
  return cell.in_slot ? "alt" : null;
}

function readStored(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
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
    if (parsed.dateTo && parsed.dateTo < fallback.dateFrom) {
      // сохранённый диапазон целиком в прошлом — открываем с сегодняшнего дня
      parsed.dateFrom = fallback.dateFrom;
      parsed.dateTo = fallback.dateTo;
    }
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
  static readonly MS_IN_DAY = 86400000;
  static readonly BUSY_RGB = "226, 56, 56";
  static readonly SLOT_RGB = "21, 92, 45";
  static readonly BUSY_MAX_ALPHA = 0.6;
  static readonly SLOT_ALPHA = 0.55;
  static readonly SLOT_ALT_ALPHA = 0.18;
  static readonly MEETING_RGB = "29, 78, 216";
  static readonly MEETING_ALPHA = 0.5;
  static readonly CELL_BASE = "#f7f7f7";
}
