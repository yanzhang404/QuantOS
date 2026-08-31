export type RadarStatus = "complete" | "partial" | "sample";

export type RadarCatalyst = {
  title: string;
  source: string;
  url: string;
};

export type RadarStock = {
  symbol: string;
  name: string;
  last_price: number;
  change_pct: number;
  relative_volume: number | null;
  turnover_pct: number | null;
  change_30m_pct: number | null;
  new_high_20d: boolean | null;
  themes: string[];
  signals: string[];
  source_url: string;
  observed_at: string;
  catalyst: RadarCatalyst | null;
  rank: number;
  heat_score: number;
  data_coverage: number;
  heat_components: {
    price_move: number;
    relative_volume: number | null;
    turnover: number | null;
    momentum_30m: number | null;
    new_high_20d: number | null;
  };
  acceleration_30m: number | null;
  acceleration_60m: number | null;
};

export type RadarTheme = {
  rank: number;
  name: string;
  heat_score: number;
  leader_score: number;
  breadth_score: number;
  data_coverage: number;
  observed_breadth: number;
  leaders: string[];
  acceleration_30m: number | null;
  acceleration_60m: number | null;
};

export type RadarSnapshot = {
  schema_version: "1.0";
  methodology_version: string;
  market: "CN";
  as_of: string;
  status: RadarStatus;
  stocks: RadarStock[];
  themes: RadarTheme[];
  summary: {
    hottest_theme: string | null;
    fastest_rising_theme: string | null;
    leader_symbol: string | null;
  };
  provenance: {
    input_sha256: string;
    generator_version: string;
    provider: string;
    stock_count: number;
    theme_count: number;
  };
};

export type RadarRefreshHealth = {
  schema_version: "1.0";
  state: "running" | "succeeded" | "failed";
  last_attempt_at: string;
  last_success_at: string | null;
  last_success_bucket: string | null;
  consecutive_failures: number;
  last_error_code: "collection_failed" | "publication_failed" | null;
  stale: boolean;
};

const apiBase =
  process.env.NEXT_PUBLIC_QUANTOS_API_URL ?? "http://localhost:8080";

export async function getLatestRadar(signal?: AbortSignal): Promise<RadarSnapshot> {
  const response = await fetch(`${apiBase}/api/v1/radar/latest`, { signal });
  if (!response.ok) {
    throw new Error(`Radar request failed with status ${response.status}.`);
  }
  return (await response.json()) as RadarSnapshot;
}

export async function getRadarHealth(
  signal?: AbortSignal,
): Promise<RadarRefreshHealth> {
  const response = await fetch(`${apiBase}/api/v1/radar/health`, { signal });
  if (!response.ok) {
    throw new Error(`Radar health request failed with status ${response.status}.`);
  }
  return (await response.json()) as RadarRefreshHealth;
}
