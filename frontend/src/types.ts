export type GridCell = {
  day_index: number;
  day: string;
  hour: number;
  minute: number;
  free_count: number;
  total: number;
  start: string;
  end: string;
  in_suggested: boolean;
};

export type GridSettings = {
  stepMinutes: number;
  slotMinutes: number;
  dateFrom: string;
  dateTo: string;
  timeFrom: string;
  timeTo: string;
};

export type SuggestedSlot = {
  start: string;
  end: string;
};

export type GridResponse = {
  date_from: string;
  date_to: string;
  total: number;
  cells: GridCell[];
  suggested: SuggestedSlot | null;
  slots: SuggestedSlot[];
  sources: Source[];
};

export type Source = {
  id: string;
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