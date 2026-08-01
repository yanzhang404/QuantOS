export type IntelligenceStatus = "complete" | "partial" | "sample";

export type IntelligenceFactor = {
  key: string;
  raw_value: number;
  unit: string;
  percentile: number;
  source: string;
  observed_at: string;
  weight: number;
  direction: "fear_when_high" | "greed_when_high";
  score: number;
  contribution: number;
};

export type IntelligenceNewsItem = {
  id: string;
  title: string;
  title_zh?: string;
  summary: string;
  summary_zh?: string;
  url: string;
  source: string;
  published_at: string;
  assets: string[];
  sentiment: number;
  confidence: number;
  relevance: number;
};

export type IntelligenceSnapshot = {
  schema_version: "1.0";
  methodology_version: string;
  date: string;
  as_of: string;
  status: IntelligenceStatus;
  score: number;
  previous_score: number | null;
  change: number | null;
  label: "extreme_fear" | "fear" | "neutral" | "greed" | "extreme_greed";
  market_score: number;
  news_score: number;
  factors: IntelligenceFactor[];
  brief: {
    title: string;
    title_zh: string;
    summary: string;
    summary_zh: string;
    highlights: string[];
    highlights_zh: string[];
    news: IntelligenceNewsItem[];
  };
  provenance: {
    input_sha256: string;
    generator_version: string;
    factor_count: number;
    news_count: number;
  };
};

const apiBase =
  process.env.NEXT_PUBLIC_QUANTOS_API_URL ?? "http://localhost:8080";

export async function getLatestIntelligence(
  signal?: AbortSignal,
): Promise<IntelligenceSnapshot> {
  const response = await fetch(`${apiBase}/api/v1/intelligence/latest`, {
    signal,
  });
  if (!response.ok) {
    throw new Error(`Intelligence request failed with status ${response.status}.`);
  }
  return (await response.json()) as IntelligenceSnapshot;
}
