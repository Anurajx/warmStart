"use client";

import { motion } from "framer-motion";
import { ListOrdered, SquareTerminal } from "lucide-react";
import { useEffect, useRef } from "react";
import type { LogLevel, PipelineLog } from "@/lib/types";

const LEVEL_META: Record<LogLevel, { label: string; cls: string }> = {
  info: { label: "INFO", cls: "text-volt-300 border-volt-500/40 bg-volt-500/10" },
  warn: { label: "WARN", cls: "text-amber-300 border-amber-500/40 bg-amber-500/10" },
  error: { label: "ERR ", cls: "text-rose-400 border-rose-500/40 bg-rose-500/10" },
  success: {
    label: "OK  ",
    cls: "text-emerald-300 border-emerald-500/40 bg-emerald-500/10",
  },
};

function formatTs(ts: number) {
  const d = new Date(ts);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `[${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${String(
    d.getMilliseconds()
  ).padStart(3, "0")}]`;
}

export function LogsPanel({ logs }: { logs: PipelineLog[] }) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs.length]);

  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: 0.1 }}
      className="overflow-hidden rounded-xl border border-ink-700 bg-ink-850/80 shadow-panel backdrop-blur"
    >
      <header className="flex items-center justify-between border-b border-ink-700 px-4 py-2.5">
        <div className="flex items-center gap-2 text-sm font-semibold tracking-wide text-slate-200">
          <span className="grid size-6 place-items-center rounded bg-volt-500/15 text-volt-400">
            <SquareTerminal size={14} />
          </span>
          Pipeline Audit Stream
          <span className="truncate font-mono text-[10px] font-normal text-slate-500">
            /warmstart/v1/events
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden items-center gap-1.5 font-mono text-[10px] text-slate-500 sm:flex">
            <ListOrdered size={11} />
            {logs.length} events
          </span>
          <span className="flex items-center gap-1.5 font-mono text-[10px] text-rose-400">
            <motion.span
              animate={{ opacity: [1, 0.2, 1] }}
              transition={{ repeat: Infinity, duration: 1.4 }}
              className="size-1.5 rounded-full bg-rose-500"
            />
            REC
          </span>
        </div>
      </header>

      <div className="terminal-scroll h-44 overflow-y-auto bg-ink-950/60 p-3 font-mono text-[11px] leading-relaxed">
        {logs.length === 0 ? (
          <p className="flex h-full items-center justify-center gap-2 text-slate-600">
            <span className="size-1.5 animate-pulseDot rounded-full bg-slate-600" />
            awaiting pipeline events…
          </p>
        ) : (
          logs.map((log, i) => {
            const meta = LEVEL_META[log.level];
            return (
              <div
                key={`${log.ts}-${i}`}
                className="flex items-start gap-2 whitespace-pre-wrap break-words py-0.5"
              >
                <span className="shrink-0 text-slate-600">{formatTs(log.ts)}</span>
                <span
                  className={`shrink-0 rounded border px-1 text-[9px] leading-4 tracking-widest ${meta.cls}`}
                >
                  {meta.label}
                </span>
                <span
                  className={
                    log.level === "error"
                      ? "text-rose-300"
                      : log.level === "warn"
                        ? "text-amber-200"
                        : log.level === "success"
                          ? "text-emerald-200"
                          : "text-slate-300"
                  }
                >
                  {log.message}
                </span>
              </div>
            );
          })
        )}
        <div ref={endRef} />
      </div>
    </motion.section>
  );
}