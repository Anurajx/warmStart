"use client";

import { motion } from "framer-motion";
import {
  Boxes,
  ChevronDown,
  Layers,
  Play,
  Send,
  Sparkles,
  Tag,
  User,
} from "lucide-react";
import { useMemo } from "react";
import type { CustomerTier } from "@/lib/types";
import { QUERY_TEMPLATES, type QueryTemplate } from "@/lib/templates";

const USERS = ["alice_doe", "carlos_g", "mira_dev", "mallory_h", "guest_42"];
const TOOLS = ["order_search", "shipping_lookup"];
const TIERS: CustomerTier[] = ["Free", "Gold"];

interface QueryFormProps {
  query: string;
  onQueryChange: (query: string) => void;
  userId: string;
  onUserIdChange: (id: string) => void;
  tier: CustomerTier;
  onTierChange: (tier: CustomerTier) => void;
  model: string;
  systemPromptVersion: string;
  tools: string[];
  onToolsChange: (tools: string[]) => void;
  running: boolean;
  onSend: () => void;
  onTemplate: (template: QueryTemplate) => void;
}

export function QueryForm({
  query,
  onQueryChange,
  userId,
  onUserIdChange,
  tier,
  onTierChange,
  model,
  systemPromptVersion,
  tools,
  onToolsChange,
  running,
  onSend,
  onTemplate,
}: QueryFormProps) {
  const sendDisabled = running || query.trim().length === 0;
  const toolOptions = useMemo(() => TOOLS, []);

  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="rounded-xl border border-ink-700 bg-ink-850/80 shadow-panel backdrop-blur"
    >
      {/* Card header */}
      <header className="flex items-center justify-between border-b border-ink-700 px-5 py-3">
        <div className="flex items-center gap-2 text-sm font-semibold tracking-wide text-slate-200">
          <span className="grid size-6 place-items-center rounded bg-volt-500/15 text-volt-400">
            <Layers size={14} />
          </span>
          Execution Console
        </div>
        <span className="rounded-full border border-ink-600 bg-ink-800 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-slate-400">
          v1 API
        </span>
      </header>

      <div className="space-y-4 p-5">
        {/* User + tier row */}
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="mb-1 flex items-center gap-1 text-[11px] font-medium uppercase tracking-wider text-slate-400">
              <User size={11} /> User ID
            </span>
            <div className="relative">
              <select
                value={userId}
                onChange={(e) => onUserIdChange(e.target.value)}
                className="w-full appearance-none rounded-lg border border-ink-600 bg-ink-900 px-3 py-2 pr-8 text-sm text-slate-100 outline-none transition focus:border-volt-500/70 focus:ring-1 focus:ring-volt-500/40"
              >
                {USERS.map((u) => (
                  <option key={u} value={u} className="bg-ink-900">
                    {u}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={14}
                className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500"
              />
            </div>
          </label>

          <div>
            <span className="mb-1 block text-[11px] font-medium uppercase tracking-wider text-slate-400">
              Customer tier
            </span>
            <div className="grid grid-cols-2 gap-1 rounded-lg border border-ink-600 bg-ink-900 p-1">
              {TIERS.map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => onTierChange(t)}
                  className={`rounded-md px-2 py-1.5 text-xs font-semibold transition ${
                    tier === t
                      ? "bg-ember-500/90 text-ink-950 shadow-glow"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Version + tools */}
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-lg border border-ink-600 bg-ink-900 px-3 py-2">
            <span className="mb-1 flex items-center gap-1 text-[11px] font-medium uppercase tracking-wider text-slate-400">
              <Tag size={11} /> System prompt
            </span>
            <span className="inline-flex items-center gap-2 font-mono text-sm font-bold text-ember-400">
              {systemPromptVersion}
              <span
                className={`size-1.5 rounded-full ${
                  systemPromptVersion.endsWith("2.0")
                    ? "bg-volt-400"
                    : "bg-ember-400"
                }`}
              />
            </span>
          </div>

          <div>
            <span className="mb-1 flex items-center gap-1 text-[11px] font-medium uppercase tracking-wider text-slate-400">
              <Boxes size={11} /> Tools
            </span>
            <div className="flex h-[38px] flex-wrap items-center gap-1.5 overflow-hidden">
              {toolOptions.map((tool) => {
                const active = tools.includes(tool);
                return (
                  <button
                    key={tool}
                    type="button"
                    onClick={() =>
                      onToolsChange(
                        active
                          ? tools.filter((t) => t !== tool)
                          : [...tools, tool]
                      )
                    }
                    className={`rounded-md border px-2 py-1 font-mono text-[10px] transition ${
                      active
                        ? "border-volt-500/60 bg-volt-500/15 text-volt-300"
                        : "border-ink-600 bg-ink-900 text-slate-500 hover:text-slate-300"
                    }`}
                  >
                    {tool}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Query textarea */}
        <label className="block">
          <span className="mb-1 block text-[11px] font-medium uppercase tracking-wider text-slate-400">
            Query
          </span>
          <div className="relative">
            <textarea
              value={query}
              onChange={(e) => onQueryChange(e.target.value)}
              rows={3}
              placeholder='e.g. "Where is my order?"'
              className="field-grid w-full resize-none rounded-lg border border-ink-600 bg-ink-900/80 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 outline-none transition focus:border-ember-500/70 focus:ring-1 focus:ring-ember-500/40"
            />
            <span className="pointer-events-none absolute bottom-2 right-2 font-mono text-[10px] text-slate-600">
              {query.length.toLocaleString()} ch
            </span>
          </div>
        </label>

        {/* Send */}
        <button
          type="button"
          onClick={onSend}
          disabled={sendDisabled}
          className="group flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-ember-500 to-ember-600 py-3 text-sm font-bold tracking-wide text-ink-950 shadow-glow transition enabled:hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {running ? (
            <>
              <motion.span
                animate={{ rotate: 360 }}
                transition={{ repeat: Infinity, duration: 0.9, ease: "linear" }}
                className="grid size-4 place-items-center"
              >
                <Play size={14} />
              </motion.span>
              Running pipeline…
            </>
          ) : (
            <>
              <Send size={15} /> Send Query
            </>
          )}
        </button>

        {/* Vendor (provider model) line */}
        <div className="flex items-center justify-between rounded-lg border border-ink-700 bg-ink-900/60 px-3 py-2">
          <span className="flex items-center gap-1.5 text-[11px] text-slate-500">
            <Sparkles size={11} className="text-volt-400" />
            Provider model
          </span>
          <span className="font-mono text-xs text-volt-300">{model}</span>
        </div>
      </div>

      {/* Quick test templates */}
      <footer className="border-t border-ink-700 p-4">
        <p className="mb-2 text-[11px] font-medium uppercase tracking-wider text-slate-400">
          Quick test templates
        </p>
        <div className="flex flex-wrap gap-1.5">
          {QUERY_TEMPLATES.map((tpl) => (
            <button
              key={tpl.id}
              type="button"
              onClick={() => onTemplate(tpl)}
              disabled={running}
              title={tpl.hint}
              className="group flex items-center gap-1.5 rounded-md border border-ink-600 bg-ink-800 px-2.5 py-1.5 text-[11px] font-medium text-slate-300 ring-volt-500/0 transition enabled:hover:border-volt-500/60 enabled:hover:text-volt-300 enabled:hover:ring-1 disabled:opacity-40"
            >
              <span className="text-slate-500 transition group-hover:text-volt-400">
                {tpl.label}
              </span>
            </button>
          ))}
        </div>
      </footer>
    </motion.section>
  );
}