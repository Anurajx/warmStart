"use client";

import { motion } from "framer-motion";
import {
  Activity,
  BrainCircuit,
  CheckCircle2,
  Clock,
  Coins,
  Layers,
  XCircle,
} from "lucide-react";
import type { QueryResult } from "@/lib/types";

interface PanelProps {
  role: "raw" | "warmstart";
  title: string;
  subtitle: string;
  icon: typeof BrainCircuit;
  result: QueryResult | null;
  pending: boolean;
}

const MATCH_META: Record<
  QueryResult["match_type"],
  { label: string; cls: string; dot: string }
> = {
  exact: {
    label: "EXACT MATCH",
    cls: "border-volt-500/50 bg-volt-500/10 text-volt-300",
    dot: "bg-volt-400",
  },
  semantic: {
    label: "SEMANTIC MATCH",
    cls: "border-ember-500/50 bg-ember-500/10 text-ember-300",
    dot: "bg-ember-400",
  },
  miss: {
    label: "CACHE MISS",
    cls: "border-rose-500/50 bg-rose-500/10 text-rose-400",
    dot: "bg-rose-500",
  },
  raw: {
    label: "LIVE PROVIDER",
    cls: "border-violet-500/50 bg-violet-500/10 text-violet-300",
    dot: "bg-violet-400",
  },
};

function Stat({
  icon: Icon,
  label,
  value,
  highlight = false,
}: {
  icon: typeof Clock;
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`flex items-center gap-2 rounded-lg border px-2.5 py-1.5 ${
        highlight ? "border-volt-500/40 bg-volt-500/10" : "border-ink-700 bg-ink-900/60"
      }`}
    >
      <Icon size={13} className={highlight ? "text-volt-300" : "text-slate-500"} />
      <span className="text-[10px] uppercase tracking-wider text-slate-500">{label}</span>
      <span
        className={`ml-auto font-mono text-xs font-semibold tabular-nums ${
          highlight ? "text-volt-300" : "text-slate-200"
        }`}
      >
        {value}
      </span>
    </div>
  );
}

function Panel({ role, title, subtitle, icon: Icon, result, pending }: PanelProps) {
  const badge = result ? MATCH_META[result.match_type] : null;
  const saved =
    result && result.match_type !== "miss" ? result.cost_saved_usd : 0;

  return (
    <div className="flex min-w-0 flex-col rounded-xl border border-ink-700 bg-ink-850/80 shadow-panel backdrop-blur">
      {/* Panel header */}
      <header className="flex items-center justify-between gap-2 border-b border-ink-700 px-4 py-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <span
            className={`grid size-7 shrink-0 place-items-center rounded-lg border ${
              role === "raw"
                ? "border-volt-500/40 bg-volt-500/10 text-volt-400"
                : "border-ember-500/40 bg-ember-500/10 text-ember-400"
            }`}
          >
            <Icon size={14} />
          </span>
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold text-slate-100">{title}</h3>
            <p className="truncate text-[11px] text-slate-500">{subtitle}</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          {pending ? (
            <span className="flex items-center gap-1.5 rounded-full border border-ink-600 bg-ink-800 px-2 py-0.5 text-[10px] text-slate-400">
              <motion.span
                animate={{ opacity: [1, 0.2, 1] }}
                transition={{ repeat: Infinity, duration: 1.2 }}
                className="size-1.5 rounded-full bg-volt-400"
              />
              RUNNING
            </span>
          ) : badge ? (
            <span
              className={`flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-semibold tracking-wide ${badge.cls}`}
            >
              <span className={`size-1.5 rounded-full ${badge.dot}`} />
              {badge.label}
            </span>
          ) : (
            <span className="rounded-full border border-ink-600 bg-ink-800 px-2 py-0.5 text-[10px] text-slate-500">
              IDLE
            </span>
          )}
        </div>
      </header>

      {/* Body */}
      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="grid grid-cols-3 gap-2">
          <Stat
            icon={Clock}
            label="Latency"
            value={result ? `${Math.round(result.latency_ms)}ms` : "—"}
            highlight={role === "warmstart" && !!result && result.match_type !== "miss"}
          />
          <Stat
            icon={Coins}
            label="Cost"
            value={result ? `$${result.cost_usd.toFixed(4)}` : "—"}
            highlight={role === "warmstart" && saved > 0}
          />
          <Stat
            icon={Activity}
            label="Tokens"
            value={result ? result.tokens.total.toLocaleString() : "—"}
          />
        </div>

        {result?.match_type === "semantic" && (
          <div className="flex items-center justify-between rounded-lg border border-ember-500/30 bg-ember-500/5 px-3 py-1.5">
            <span className="text-[10px] uppercase tracking-wider text-ember-300/80">
              Semantic similarity
            </span>
            <span className="font-mono text-xs font-semibold text-ember-300">
              {(result.similarity ?? 0).toFixed(4)}
            </span>
          </div>
        )}

        {result && result.match_type !== "miss" && result.match_type !== "raw" && (
          <div className="flex items-center justify-between rounded-lg border border-volt-500/25 bg-volt-500/5 px-3 py-1.5">
            <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-volt-300/80">
              <CheckCircle2 size={11} /> Money saved on this query
            </span>
            <span className="font-mono text-xs font-semibold text-volt-300">
              ${saved.toFixed(4)}
            </span>
          </div>
        )}

        <div className="terminal-scroll min-h-[140px] flex-1 overflow-y-auto rounded-lg border border-ink-700 bg-ink-900/70 p-3">
          {pending ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <motion.div
                  key={i}
                  animate={{ opacity: [0.4, 0.9, 0.4] }}
                  transition={{ repeat: Infinity, duration: 1.6, delay: i * 0.2 }}
                  className="h-3 rounded bg-ink-700"
                  style={{ width: `${92 - i * 14}%` }}
                />
              ))}
            </div>
          ) : result ? (
            <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-slate-200">
              {result.answer}
            </p>
          ) : (
            <p className="flex h-full items-center justify-center gap-2 text-xs text-slate-600">
              <XCircle size={14} />
              No query yet — the pipeline output will render here
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

export function SideBySideView({
  raw,
  warm,
  pendingRaw,
  pendingWarm,
}: {
  raw: QueryResult | null;
  warm: QueryResult | null;
  pendingRaw: boolean;
  pendingWarm: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: 0.05 }}
    >
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-semibold tracking-wide text-slate-200">
          <span className="grid size-6 place-items-center rounded bg-ember-500/15 text-ember-400">
            <BrainCircuit size={14} />
          </span>
          Comparative Pipeline View
        </div>
        <div className="flex items-center gap-3 font-mono text-[10px] text-slate-500">
          <span className="flex items-center gap-1.5">
            <span className="size-1.5 rounded-full bg-volt-400" />
            CONTROL PATH
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-1.5 rounded-full bg-ember-400" />
            WARMSTART PATH
          </span>
          <span className="hidden items-center gap-1.5 sm:flex">
            <Layers size={11} /> L1 EXACT · L2 VECTOR
          </span>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <Panel
          role="raw"
          title="Baseline · Live Provider"
          subtitle="Direct LLM inference — the control path"
          icon={BrainCircuit}
          result={raw}
          pending={pendingRaw}
        />
        <Panel
          role="warmstart"
          title="Warmstart · Redis Firewall"
          subtitle="Exact → vector → provider fallback"
          icon={Layers}
          result={warm}
          pending={pendingWarm}
        />
      </div>
    </motion.div>
  );
}