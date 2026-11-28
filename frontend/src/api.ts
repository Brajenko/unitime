import type { AvailabilityWindow, Connection, GridResponse, GridSettings, Meeting, ProviderInfo, Team, User } from "./types";
import { BROWSER_TZ } from "./tz";

export class UnauthorizedError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const detail = await _readDetail(response);
    if (response.status === 401 && !path.startsWith("/api/auth/")) {
      throw new UnauthorizedError(detail);
    }
    throw new Error(detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export function fetchGrid(settings: GridSettings, teamId: string | null = null): Promise<GridResponse> {
  const query = new URLSearchParams({
    date_from: settings.dateFrom,
    date_to: settings.dateTo,
    step_minutes: String(settings.stepMinutes),
    slot_minutes: String(settings.slotMinutes),
    time_from: settings.timeFrom,
    time_to: settings.timeTo,
    tz: BROWSER_TZ,
  });
  if (teamId) {
    query.set("team_id", teamId);
  }
  return request(`/api/grid?${query.toString()}`);
}

export function fetchConnections(): Promise<Connection[]> {
  return request("/api/connections");
}

export function fetchConnection(id: string): Promise<Connection> {
  return request(`/api/connections/${id}`);
}

export function fetchProviders(): Promise<ProviderInfo[]> {
  return request("/api/providers");
}

export function connectApple(email: string, appPassword: string): Promise<Connection> {
  return request("/api/connections/apple", {
    method: "POST",
    body: JSON.stringify({ email, app_password: appPassword }),
  });
}

export function selectCollections(connectionId: string, selectedIds: string[]): Promise<Connection> {
  return request(`/api/connections/${connectionId}/collections`, {
    method: "PATCH",
    body: JSON.stringify({ selected_ids: selectedIds }),
  });
}

export function deleteConnection(connectionId: string): Promise<void> {
  return request(`/api/connections/${connectionId}`, { method: "DELETE" });
}

export function enqueueSync(
  connectionId: string,
  dateFrom: string,
  dateTo: string,
): Promise<{ ok: boolean; job_id: string }> {
  return request(`/api/connections/${connectionId}/sync?date_from=${dateFrom}&date_to=${dateTo}`, {
    method: "POST",
  });
}

export function fetchSyncJob(
  connectionId: string,
  jobId: string,
): Promise<{ status: "queued" | "running" | "succeeded" | "failed" }> {
  return request(`/api/connections/${connectionId}/sync/${jobId}`);
}

export function fetchMe(): Promise<User> {
  return request("/api/me");
}

export function login(email: string, password: string): Promise<User> {
  return request("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
}

export function register(email: string, password: string): Promise<User> {
  return request("/api/auth/register", { method: "POST", body: JSON.stringify({ email, password }) });
}

export function logout(): Promise<void> {
  return request("/api/auth/logout", { method: "POST" });
}

export function fetchTeams(): Promise<Team[]> {
  return request("/api/teams");
}

export function createTeam(name: string): Promise<Team> {
  return request("/api/teams", { method: "POST", body: JSON.stringify({ name }) });
}

export function joinTeam(inviteToken: string): Promise<Team> {
  return request("/api/teams/join", { method: "POST", body: JSON.stringify({ invite_token: inviteToken }) });
}

export function fetchMeetings(teamId: string): Promise<Meeting[]> {
  return request(`/api/teams/${teamId}/meetings`);
}

export function createMeeting(teamId: string, start: string, end: string, title: string): Promise<Meeting> {
  return request(`/api/teams/${teamId}/meetings`, {
    method: "POST",
    body: JSON.stringify({ start, end, title: title.trim() || null }),
  });
}

export function cancelMeeting(meetingId: string): Promise<void> {
  return request(`/api/meetings/${meetingId}`, { method: "DELETE" });
}

function availabilityQuery(settings: GridSettings): string {
  return new URLSearchParams({ date_from: settings.dateFrom, date_to: settings.dateTo, tz: BROWSER_TZ }).toString();
}

export function fetchAvailability(settings: GridSettings): Promise<AvailabilityWindow[]> {
  return request(`/api/me/availability?${availabilityQuery(settings)}`);
}

export function saveAvailability(settings: GridSettings, windows: AvailabilityWindow[]): Promise<AvailabilityWindow[]> {
  return request(`/api/me/availability?${availabilityQuery(settings)}`, {
    method: "PUT",
    body: JSON.stringify({ windows }),
  });
}

export function connectLink(url: string): Promise<Connection> {
  return request("/api/connections/link", { method: "POST", body: JSON.stringify({ url }) });
}

async function _readDetail(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
  } catch {
    return response.statusText;
  }
  return response.statusText;
}
