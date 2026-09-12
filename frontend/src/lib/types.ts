export type MatchType = "exact" | "semantic" | "miss" | "raw";
export type CustomerTier = "Free" | "Gold";
export type LogLevel = "info" | "warn" | "error" | "success";

export interface TokenUsage {
  input: number;
  output: number;
  embedding: number;
  total: number;
}

export interface PipelineLog {
  ts: number;
  level: LogLevel;
  message: string;
}

export interface QueryPayload {
  query: string;
  user_id: string;
  customer_tier: CustomerTier;
  system_prompt_version: string;
  tools: string[];
  model: string;
}

export interface QueryResult {
  query: string;
  answer: string;
  match_type: MatchType;
  similarity: number | null;
  latency_ms: number;
  cost_usd: number;
  cost_saved_usd: number;
  tokens: TokenUsage;
  cached: boolean;
  events: PipelineLog[];
}

export interface Metrics {
  requests: number;
  hits: number;
  misses: number;
  exact_hits: number;
  semantic_hits: number;
  hit_rate_pct: number;
  total_money_saved_usd: number;
  raw_avg_latency_ms: number;
  warmstart_avg_latency_ms: number;
  latency_reduction_pct: number;
  evaluations: number;
  false_hits: number;
  false_hit_rate_pct: number;
  cache_entries: number;
}

export interface BustCacheResult {
  system_prompt_version: string;
  keys_deleted: number;
  deleted: string[];
}

export interface HealthStatus {
  status: "ok" | "degraded";
  redis: boolean;
  llm: boolean;
  version: string;
}