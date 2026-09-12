"use client";

import { motion } from "framer-motion";
import {
  AlertTriangle,
  Cpu,
  Flame,
  RefreshCcw,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  bustCache,
  getHealth,
  getMetrics,
  runRawQuery,
  runWarmstart,
} from "@/lib/api";
import type {
  CustomerTier,
  HealthStatus,
  LogLevel,
  Metrics,
  PipelineLog,
  QueryPayload,
  QueryResult,
} from "@/lib/types";
import type { QueryTemplate } from "@/lib/templates";
import { LogsPanel } from "./LogsPanel";
import { MetricCards } from "./MetricCards";
import { QueryForm } from "./QueryForm";
import { SideBySideView } from "./SideBySideView";

const MODEL = "gpt-4o-mini";

export function Dashboard() {
  const [query, setQuery] = useState("Where is my order?");
  const [userId, setUserId] = useState("alice_doe");
  const [tier, setTier] = useState<CustomerTier>("Free");
  const [version, setVersion] = useState("v1.0");
  const [tools, setTools] = useState<string[]>([]);
  const [model] = useState(MODEL);

  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [raw, setRaw] = useState<QueryResult | null>(null);
  const [warm, setWarm] = useState<QueryResult | null>(null);
  const [pendingRaw, setPendingRaw] = useState(false);
  const [pendingWarm, setPendingWarm] = useState(false);
  const [busting, setBusting] = useState(false);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<PipelineLog[]>([]);

  const busyRef = useRef(false);

  const appendLog = useCallback(
    (level: LogLevel, message: string) => {
      setLogs((prev) => [...prev.slice(-299), { ts: Date.now(), level, message }]);
    },
    []
  );

  const refreshMetrics = useCallback(async () => {
    try {
      const m = await getMetrics();
      setMetrics(m);
    } catch {
      /* keep last-known metrics */
    }
  }, []);

  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await getHealth());
    } catch {
      setHealth({ status: "degraded", redis: false, llm: false, version: "?" });
    }
  }, []);

  // Boot: greet + start metric polling.
  useEffect(() => {
    appendLog("info", "warmstart firewall · dashboard connected");
    appendLog("info", `provider ${MODEL} · threshold 0.78 · distance cosine`);
    void refreshMetrics();
    void refreshHealth();
    const t = setInterval(() => void refreshMetrics(), 4000);
    return () => clearInterval(t);
  }, [appendLog, refreshMetrics, refreshHealth]);

  const buildPayload = useCallback(
    (overrides: Partial<QueryPayload> = {}): QueryPayload => ({
      query,
      user_id: userId,
      customer_tier: tier,
      system_prompt_version: version,
      tools,
      model,
      ...overrides,
    }),
    [query, userId, tier, version, tools, model]
  );

  const send = useCallback(
    async (payload: QueryPayload) => {
      if (busyRef.current) return;
      busyRef.current = true;
      setError(null);
      setPendingRaw(true);
      setPendingWarm(true);

      const short = payload.query.length > 48
        ? `${payload.query.slice(0, 48)}…`
        : payload.query;
      appendLog(
        "info",
        `➤ firing control + warmstart for "${short}" (user=${payload.user_id}, tier=${payload.customer_tier}, v${payload.system_prompt_version}, tools=[${payload.tools.join(",")}])`
      );

      const [rawRes, warmRes] = await Promise.allSettled([
        runRawQuery(payload),
        runWarmstart(payload),
      ]);

      setPendingRaw(false);
      setPendingWarm(false);

      if (rawRes.status === "fulfilled") {
        setRaw(rawRes.value);
        rawRes.value.events.forEach((e) => appendLog(e.level, e.message));
      } else {
        setError((rawRes.reason as Error).message);
        appendLog("error", `control path failed: ${(rawRes.reason as Error).message}`);
      }

      if (warmRes.status === "fulfilled") {
        setWarm(warmRes.value);
        warmRes.value.events.forEach((e) => appendLog(e.level, e.message));
      } else {
        setError((warmRes.reason as Error).message);
        appendLog("error", `warmstart path failed: ${(warmRes.reason as Error).message}`);
      }

      if (rawRes.status === "fulfilled" && warmRes.status === "fulfilled") {
        const r = rawRes.value;
        const w = warmRes.value;
        const delta = Math.max(0, r.latency_ms - w.latency_ms);
        appendLog(
          "success",
          `✓ compared · latency ${Math.round(r.latency_ms)}ms → ${Math.round(w.latency_ms)}ms (Δ ${Math.round(delta)}ms) · cost $${r.cost_usd.toFixed(4)} → $${w.cost_usd.toFixed(4)} · match=${w.match_type}`
        );
      }

      void refreshMetrics();
      busyRef.current = false;
    },
    [appendLog, refreshMetrics]
  );

  const handleSend = useCallback(() => {
    void send(buildPayload());
  }, [send, buildPayload]);

  const handleTemplate = useCallback(
    (tpl: QueryTemplate) => {
      const next = buildPayload({
        query: tpl.query ? tpl.query : query,
        user_id: tpl.user_id ?? userId,
        customer_tier: tpl.customer_tier ?? tier,
        system_prompt_version: tpl.system_prompt_version ?? version,
        tools: tpl.tools ?? tools,
      });
      setQuery(tpl.query ? tpl.query : query);
      if (tpl.user_id) setUserId(tpl.user_id);
      if (tpl.customer_tier) setTier(tpl.customer_tier);
      if (tpl.system_prompt_version) setVersion(tpl.system_prompt_version);
      if (tpl.tools) setTools(tpl.tools);
      if (tpl.query !== query || tpl.user_id || tpl.customer_tier || tpl.tools || tpl.system_prompt_version) {
        appendLog("warn", `◆ template: ${tpl.label} — ${tpl.hint}`);
      }
      void send(next);
    },
    [buildPayload, send, appendLog, query, userId, tier, version, tools]
  );

  const handleBust = useCallback(async () => {
    if (version !== "v1.0") return;
    setBusting(true);
    appendLog("warn", `ADMIN: busting cache for system prompt ${version}…`);
    try {
      const res = await bustCache(version);
      appendLog(
        "success",
        `ADMIN: invalidated ${res.keys_deleted} key${res.keys_deleted === 1 ? "" : "s"} for ${res.system_prompt_version}`
      );
      setVersion("v2.0");
      appendLog(
        "warn",
        "ADMIN: deployed prompt v2.0 — composite namespace changed; all sessions see cold cache"
      );
      await refreshMetrics();
      await refreshHealth();
    } catch (e) {
      const msg = (e as Error).message;
      setError(msg);
      appendLog("error", `ADMIN: bust failed — ${msg}`);
    } finally {
      setBusting(false);
    }
  }, [version, appendLog, refreshMetrics, refreshHealth]);

  const healthDots = health
    ? [
        { name: "redis", ok: health.redis },
        { name: "llm", ok: health.llm },
      ]
    : [
        { name: "redis", ok: null },
        { name: "llm", ok: null },
      ];

  return (
    <div className="mx-auto max-w-7xl space-y-4 px-4 py-6">
      {/* Top bar */}
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <motion.div
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          className="flex items-center gap-3"
        >
          <span className="clip-notch grid size-11 place-items-center rounded-lg bg-gradient-to-br from-ember-400 to-ember-600 shadow-glow">
            <Flame size={22} className="text-ink-950" />
          </span>
          <div>
            <h1 className="font-mono text-xl font-bold tracking-tight text-slate-50">
              WARMSTART
            </h1>
            <p className="text-xs text-slate-500">
              Redis vector firewall for LLM latency &amp; cost
            </p>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, x: 8 }}
          animate={{ opacity: 1, x: 0 }}
          className="flex flex-wrap items-center gap-2"
        >
          <div className="flex items-center gap-3 rounded-lg border border-ink-700 bg-ink-850/80 px-3 py-2">
            {healthDots.map((h) => (
              <span key={h.name} className="flex items-center gap-1.5 font-mono text-[10px] text-slate-400">
                <span
                  className={`size-1.5 rounded-full ${
                    h.ok === null ? "animate-pulseDot bg-slate-500"
                    : h.ok ? "bg-emerald-400"
                    : "bg-rose-500"
                  }`}
                />
                {h.name.toUpperCase()}
              </span>
            ))}
            <span className="hidden font-mono text-[10px] text-slate-500 sm:inline">
              v{health?.version ?? "–"}
            </span>
          </div>

          <button
            type="button"
            onClick={() => void handleBust()}
            disabled={version !== "v1.0" || busting}
            title={
              version !== "v1.0"
                ? "Deployed — cache namespace already fresh"
                : "Purge all warmstart keys for v1.0 and deploy v2.0"
            }
            className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-100 ${
              version !== "v1.0"
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
                : "border-rose-500/40 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20"
            }`}
          >
            {version === "v1.0" ? (
              busting ? (
                <RefreshCcw size={13} className="animate-spin" />
              ) : (
                <Trash2 size={13} />
              )
            ) : (
              <Cpu size={13} />
            )}
            {version === "v1.0"
              ? busting
                ? "Busting…"
                : "Bust Cache · Deploy v2.0"
              : "v2.0 deployed"}
          </button>
        </motion.div>
      </header>

      {/* Metric cards */}
      <MetricCards metrics={metrics} />

      {/* Error banner */}
      {error && (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-2 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300"
        >
          <AlertTriangle size={13} />
          {error}
        </motion.div>
      )}

      {/* Execution console + comparison view */}
      <div className="grid gap-4 lg:grid-cols-[400px_1fr]">
        <QueryForm
          query={query}
          onQueryChange={setQuery}
          userId={userId}
          onUserIdChange={setUserId}
          tier={tier}
          onTierChange={setTier}
          model={model}
          systemPromptVersion={version}
          tools={tools}
          onToolsChange={setTools}
          running={pendingRaw || pendingWarm}
          onSend={() => void handleSend()}
          onTemplate={(tpl) => void handleTemplate(tpl)}
        />
        <SideBySideView
          raw={raw}
          warm={warm}
          pendingRaw={pendingRaw}
          pendingWarm={pendingWarm}
        />
      </div>

      {/* Log stream */}
      <LogsPanel logs={logs} />
    </div>
  );
}