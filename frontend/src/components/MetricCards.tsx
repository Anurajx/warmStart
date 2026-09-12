"use client";

import { motion } from "framer-motion";
import {
  DollarSign,
  Gauge,
  Percent,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Metrics } from "@/lib/types";

const FALSE_HIT_BUDGET = 1.0; // %

function useAnimatedNumber(value: number, duration = 0.7) {
  const [display, setDisplay] = useState(value);
  const fromRef = useRef(value);
  useEffect(() => {
    const from = fromRef.current;
    if (from === value) return;
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / (duration * 1000));
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(from + (value - from) * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
      else fromRef.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);
  return display;
}

interface MetricCardProps {
  title: string;
  icon: LucideIcon;
  accent: string;
  value: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  sublabel: string;
  status?: { tone: "good" | "bad"; label: string } | null;
}

function MetricCard({
  title,
  icon: Icon,
  accent,
  value,
  decimals = 1,
  prefix = "",
  suffix = "",
  sublabel,
  status = null,
}: MetricCardProps) {
  const animated = useAnimatedNumber(value);
  return (
    <motion.article
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="relative overflow-hidden rounded-xl border border-ink-700 bg-ink-850/80 p-4 shadow-panel backdrop-blur"
    >
      <div
        className={`pointer-events-none absolute -right-6 -top-8 size-24 rounded-full blur-2xl ${accent}`}
      />
      <div className="flex items-start justify-between">
        <p className="text-[11px] font-medium uppercase tracking-widest text-slate-400">
          {title}
        </p>
        <span
          className={`grid size-7 place-items-center rounded-lg border border-ink-600 ${accent} bg-opacity-10`}
        >
          <Icon size={14} />
        </span>
      </div>
      <p className="mt-2 font-mono text-3xl font-bold tabular-nums text-slate-50">
        {prefix}
        {animated.toLocaleString(undefined, {
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals,
        })}
        {suffix}
      </p>
      <div className="mt-2 flex items-center justify-between gap-2">
        <p className="truncate text-[11px] text-slate-500">{sublabel}</p>
        {status && (
          <span
            className={`shrink-0 rounded-full border px-2 py-0.5 font-mono text-[10px] font-semibold tracking-wide ${
              status.tone === "good"
                ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
                : "border-rose-500/40 bg-rose-500/10 text-rose-400"
            }`}
          >
            {status.label}
          </span>
        )}
      </div>
    </motion.article>
  );
}

export function MetricCards({ metrics }: { metrics: Metrics | null }) {
  const hitRate = metrics?.hit_rate_pct ?? 0;
  const latencyReduction = metrics?.latency_reduction_pct ?? 0;
  const moneySaved = metrics?.total_money_saved_usd ?? 0;
  const falseHitRate = metrics?.false_hit_rate_pct ?? 0;
  const evaluations = metrics?.evaluations ?? 0;

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard
        title="Total Money Saved"
        icon={DollarSign}
        accent="text-ember-400 bg-ember-500/10"
        value={moneySaved}
        decimals={2}
        prefix="$"
        sublabel={`${metrics?.hits ?? 0} cache hits served`}
      />
      <MetricCard
        title="Latency Reduction"
        icon={Gauge}
        accent="text-volt-400 bg-volt-500/10"
        value={latencyReduction}
        suffix="%"
        sublabel={
          metrics?.raw_avg_latency_ms
            ? `${metrics.warmstart_avg_latency_ms?.toFixed(1) ?? "–"}ms vs ${metrics.raw_avg_latency_ms.toFixed(1)}ms avg`
            : "no comparisons yet"
        }
      />
      <MetricCard
        title="Cache Hit Rate"
        icon={Percent}
        accent="text-emerald-400 bg-emerald-500/10"
        value={hitRate}
        suffix="%"
        sublabel={`${metrics?.requests ?? 0} warmstart requests`}
      />
      <MetricCard
        title="False Hit Rate"
        icon={ShieldAlert}
        accent="text-rose-400 bg-rose-500/10"
        value={falseHitRate}
        suffix="%"
        sublabel={`${evaluations} judge evaluations`}
        status={
          evaluations === 0
            ? { tone: "good", label: "AWAITING EVAL" }
            : falseHitRate < FALSE_HIT_BUDGET
              ? { tone: "good", label: "NOMINAL <1.0%" }
              : { tone: "bad", label: "BREACH" }
        }
      />
    </div>
  );
}