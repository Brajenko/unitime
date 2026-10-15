import type { Connection, GridResponse, GridSettings, ProviderInfo, Team, User } from "./types";

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

export function enqueueSync(connectionId: string, dateFrom: string, dateTo: string): Promise<{ ok: boolean }> {
  return request(`/api/connections/${connectionId}/sync?date_from=${dateFrom}&date_to=${dateTo}`, {
    method: "POST",
  });
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
