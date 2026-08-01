import coverage from "./multi-timeframe-coverage.v1.json";

export type CoverageInterval = "5m" | "15m" | "1h" | "4h" | "1d";
export type CoverageSymbol = "BTCUSDT" | "ETHUSDT";

type CoverageMember = {
  symbol: CoverageSymbol;
  interval: CoverageInterval;
  dataset_version: string;
  content_sha256: string;
  row_count: number;
  missing_interval_count: number;
  status: "verified";
};

type CoverageEvidence = {
  schema_version: "dataset-coverage.v1";
  bundle_version: string;
  requested_start: string;
  requested_end: string;
  member_count: number;
  total_row_count: number;
  missing_interval_count: number;
  members: CoverageMember[];
};

export const marketDataCoverage = coverage as CoverageEvidence;
export const coverageIntervals: CoverageInterval[] = ["5m", "15m", "1h", "4h", "1d"];

export function getCoverageMember(
  symbol: CoverageSymbol,
  interval: CoverageInterval,
): CoverageMember {
  const member = marketDataCoverage.members.find(
    (candidate) => candidate.symbol === symbol && candidate.interval === interval,
  );
  if (!member) {
    throw new Error(`missing coverage member: ${symbol}/${interval}`);
  }
  return member;
}
