import type { Connection, GridResponse, GridSettings, ProviderInfo } from "./types";

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
    throw new Error(detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export function fetchGrid(settings: GridSettings): Promise<GridResponse> {
  const query = new URLSearchParams({
    date_from: settings.dateFrom,
    date_to: settings.dateTo,
    step_minutes: String(settings.stepMinutes),
    slot_minutes: String(settings.slotMinutes),
    time_from: settings.timeFrom,
    time_to: settings.timeTo,
  });
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

export function enqueueSync(connectionId: string, dateFrom: string, dateTo: string): Promise<{ ok: boolean }> {
  return request(`/api/connections/${connectionId}/sync?date_from=${dateFrom}&date_to=${dateTo}`, {
    method: "POST",
  });
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
