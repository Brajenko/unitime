export type GridCell = {
  day_index: number;
  day: string;
  hour: number;
  minute: number;
  free_count: number;
  total: number;
  start: string;
  end: string;
  slot_start: boolean;
  in_slot: boolean;
};

export type GridSettings = {
  stepMinutes: number;
  slotMinutes: number;
  dateFrom: string;
  dateTo: string;
  timeFrom: string;
  timeTo: string;
};

export type GridResponse = {
  date_from: string;
  date_to: string;
  total: number;
  cells: GridCell[];
  slot_minutes: number;
  step_minutes: number;
  sources: Source[];
  members: GridMember[];
  team_id: string | null;
};

export type Source = {
  id: string;
  connection_id: string;
  name: string;
  provider: string;
  selected: boolean;
  status: string;
  account_email: string | null;
  last_error: string | null;
};

export type Collection = {
  id: string;
  name: string;
  selected: boolean;
};

export type Connection = {
  id: string;
  provider: string;
  status: string;
  account_email: string | null;
  last_error: string | null;
  collections: Collection[];
};

export type ProviderInfo = {
  id: string;
  name: string;
  oauth: boolean;
};

export type User = {
  id: string;
  email: string;
};

export type TeamMember = {
  user_id: string;
  email: string;
};

export type Team = {
  id: string;
  name: string;
  invite_token: string;
  is_owner: boolean;
  members: TeamMember[];
};

export type GridMember = {
  user_id: string;
  email: string;
  calendars: number;
  last_synced_at: string | null;
  in_overlay: boolean;
};
