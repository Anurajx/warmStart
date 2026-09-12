"""LLM-as-judge evaluation of semantic cache hits (false-hit detection).

Every semantic hit is re-checked asynchronously by a cheap judge model. The
judge decides whether the cached answer is a factually valid reply to the
incoming (paraphrased) query. False hits are counted and surfaced on the
metrics endpoint so cache quality degrades loudly, never silently.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

from openai import OpenAI
from redis import Redis

from .cache_engine import CachedDocument, METRICS_KEY, estimate_tokens
from .config import Settings, get_settings

logger = logging.getLogger("warmstart.evaluator")

JUDGE_SYSTEM_PROMPT = (
    "You are a strict semantic-cache quality auditor. A caching layer returned "
    "a previously generated answer for a NEW incoming user query based on "
    "vector similarity. Decide whether the CACHED ANSWER is a factually valid, "
    "complete and on-topic reply to the INCOMING QUERY.\n"
    "Guidelines:\n"
    "- TRUE if the answer resolves the intent of the incoming query correctly, "
    "even if the wording differs.\n"
    "- FALSE if the answer misunderstands the query, is about a different "
    "subject, contradicts the query, or omits critical requested information.\n"
    "Respond with STRICT JSON only: {\"verdict\": true|false, \"reason\": \"<one sentence>\"}"
)

Verdict = tuple[bool, str, int, int]


class HitEvaluator:
    """Background evaluator that scores semantic hits with a judge model."""

    def __init__(
        self,
        redis: Redis,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.redis = redis

        kwargs: dict[str, str] = {"api_key": self.settings.openai_api_key}
        if self.settings.openai_base_url:
            kwargs["base_url"] = self.settings.openai_base_url
        self.judge = OpenAI(**kwargs) if self.settings.openai_api_key else None

    async def evaluate(self, cached: CachedDocument, incoming_query: str) -> None:
        """Schedule a blocking judge call off the event loop."""
        if self.judge is None:
            logger.warning("Judge unavailable (no API key); skipping evaluation")
            return
        try:
            verdict, reason, input_tokens, output_tokens = await asyncio.to_thread(
                self._judge, cached, incoming_query
            )
        except Exception as exc:  # OpenAI errors, malformed response, ...
            logger.error("Semantic-hit evaluation failed: %s", exc)
            return

        if not verdict:
            self.redis.hincrby(METRICS_KEY, "false_hits", 1)
        self.redis.hincrby(METRICS_KEY, "evaluations", 1)

        self._append_evaluation(cached, incoming_query, verdict, reason)
        level = "error" if not verdict else "info"
        getattr(logger, level)(
            "Judge verdict on %s hit for %r: %s — %s",
            "semantic", incoming_query[:40], verdict, reason,
        )

    # -- internals ---------------------------------------------------------

    def _judge(self, cached: CachedDocument, incoming_query: str) -> Verdict:
        response = self.judge.chat.completions.create(
            model=self.settings.judge_model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "incoming_query": incoming_query,
                            "cached_query_that_produced_the_answer": cached.stored_query,
                            "cached_answer": cached.answer,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or '{"verdict": false}'
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            data = {}
        usage = response.usage
        verdict = bool(data.get("verdict", False))
        reason = str(data.get("reason", "no reason supplied"))
        return (
            verdict,
            reason,
            usage.prompt_tokens if usage else estimate_tokens(incoming_query),
            usage.completion_tokens if usage else 0,
        )

    def _append_evaluation(
        self,
        cached: CachedDocument,
        incoming_query: str,
        verdict: bool,
        reason: str,
    ) -> None:
        entry = {
            "id": uuid.uuid4().hex[:12],
            "ts": time.time(),
            "namespace": cached.namespace,
            "similarity": cached.similarity,
            "incoming_query": incoming_query,
            "cached_query": cached.stored_query,
            "verdict": verdict,
            "reason": reason,
        }
        key = f"{self.settings.redis_key_prefix}:evaluations"
        self.redis.lpush(key, json.dumps(entry, default=str))
        self.redis.ltrim(key, 0, 199)