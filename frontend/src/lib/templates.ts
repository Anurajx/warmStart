import type { CustomerTier } from "./types";

export interface QueryTemplate {
  id: string;
  label: string;
  hint: string;
  query: string;
  user_id?: string;
  customer_tier?: CustomerTier;
  system_prompt_version?: string;
  tools?: string[];
}

/**
 * Quick-test presets mapped to demo scenarios:
 * exact hit, semantic paraphrase hit, cross-user isolation, prompt deploy.
 */
export const QUERY_TEMPLATES: QueryTemplate[] = [
  {
    id: "exact",
    label: "Exact hit",
    hint: 'Same query string → Layer 1 hash match (~5ms)',
    query: "Where is my order?",
  },
  {
    id: "semantic",
    label: "Semantic match",
    hint: 'Paraphrase → Layer 2 vector hit (same user/tier)',
    query: "Track my package",
  },
  {
    id: "tenant",
    label: "User context separation",
    hint: "New tenant namespace → identical query must MISS",
    query: "Where is my order?",
    user_id: "mallory_h",
  },
  {
    id: "opposite_tier",
    label: "Tier isolation",
    hint: "Gold tier → different composite key namespace",
    query: "Where is my order?",
    customer_tier: "Gold",
  },
  {
    id: "deploy",
    label: "Prompt update",
    hint: "Same query, v2.0 → fresh namespace (paranoia mode)",
    query: "Where is my order?",
    system_prompt_version: "v2.0",
  },
  {
    id: "tools",
    label: "Tools change",
    hint: "Adding a tool reshapes the composite key",
    query: "Where is my order?",
    tools: ["shipping_lookup"],
  },
];