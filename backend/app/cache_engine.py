"""Three-layer execution pipeline for Warmstart.

Layer 1 - Exact match    : Redis key/value lookup on a raw text hash (~5ms).
Layer 2 - Semantic match : Embed the query, cosine-KNN search the vector index
                           inside the tenant+config namespace (threshold based).
Layer 3 - Cache miss     : Call the OpenAI model, persist answer + embedding.

Key architecture
----------------
Every query is scoped by a tenant namespace derived from:

    composite = MD5(model | system_prompt_version | tools | customer_tier)
    namespace = sha256(user_id)[:12] + "-" + composite

The composite isolates unrelated configurations (model bumps, prompt deploys,
tool changes, tier upgrades). The user suffix guarantees cross-tenant/cross-user
semantic isolation: vectors for one user can never be returned to another.
Both layers share the namespace, and keying the vector index prefix with the
prompt version makes "bust by version" a trivial prefix scan.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI
from redis import Redis
from redisvl.index import SearchIndex
from redisvl.query import VectorQuery
from redisvl.query.filter import Tag

from .config import CustomerTier, Settings, get_settings

logger = logging.getLogger("warmstart.cache")

MetricRecord = dict[str, float]
METRICS_KEY = "warmstart:metrics"

# Stable, tier-scoped system prompts. Because the prefix is identical across
# requests, OpenAI's automatic prompt caching (>=1024 token prefix) engages on
# the provider side too, further cutting input costs on Layer 3.
SYSTEM_PROMPTS: dict[CustomerTier, str] = {
    "Free": (
        "You are Warmstart support. Answer concisely; one or two sentences. "
        "Be polite, accurate and never invent shipping facts."
    ),
    "Gold": (
        "You are Warmstart premium support. Answer thoroughly with actionable "
        "next steps. Include the order reference and expected delivery window "
        "when available. Be warm and precise."
    ),
}


@dataclass
class TokenUsage:
    """Token breakdown for a single pipeline run."""

    input: int = 0
    output: int = 0
    embedding: int = 0

    @property
    def total(self) -> int:
        return self.input + self.output

    def as_dict(self) -> dict[str, int]:
        return {
            "input": self.input,
            "output": self.output,
            "embedding": self.embedding,
            "total": self.total,
        }


@dataclass
class LogEvent:
    """A single, timestamped audit-log entry produced by the pipeline."""

    ts: float
    level: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {"ts": self.ts, "level": self.level, "message": self.message}


@dataclass
class RequestContext:
    """Normalised inbound query context from the API layer."""

    query: str
    user_id: str
    customer_tier: CustomerTier
    system_prompt_version: str
    tools: list[str]
    model: str

    @property
    def system_prompt(self) -> str:
        prompt = SYSTEM_PROMPTS[self.customer_tier]
        if self.tools:
            prompt += f"\n\nAvailable tools: {', '.join(self.tools)}"
        return prompt


@dataclass
class CachedDocument:
    """Metadata resolved from a cache hit, used by the LLM judge."""

    answer: str
    stored_query: str
    namespace: str
    input_tokens: int
    output_tokens: int
    similarity: float
    redis_key: str = ""


@dataclass
class PipelineResult:
    """Result of a raw or warmstart pipeline execution."""

    answer: str
    match_type: str
    latency_ms: float
    cost_usd: float
    cost_saved_usd: float
    similarity: float | None
    tokens: dict[str, int]
    cached: bool
    events: list[dict[str, Any]] = field(default_factory=list)
    cached_doc: CachedDocument | None = field(default=None)


class CacheKey:
    """Composite key construction and tenant namespacing."""

    @staticmethod
    def _slug(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def composite_hash(
        model: str, system_prompt_version: str, tools: list[str], tier: str
    ) -> str:
        """MD5(model + system_prompt_version + tools + customer_tier)."""
        canonical_tools = json.dumps(sorted(tools), separators=(",", ":"))
        payload = "|".join((model, system_prompt_version, canonical_tools, tier))
        return hashlib.md5(payload.encode("utf-8")).hexdigest()

    @classmethod
    def namespace(cls, user_id: str, composite: str) -> str:
        """Hex-only namespace: tenant slug + config composite (tag-safe)."""
        return f"{cls._slug(user_id)}-{composite}"

    @classmethod
    def document_id(cls, query: str) -> str:
        return hashlib.sha1(query.encode("utf-8")).hexdigest()[:16]


def estimate_tokens(text: str) -> int:
    """Heuristic token count (~4 chars/token); used only for cost estimates."""
    return max(1, len(text) // 4)


class WarmstartCacheEngine:
    """Owns the Redis connection, vector index and the OpenAI clients."""

    def __init__(
        self,
        redis: Redis | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.redis = redis or Redis.from_url(
            self.settings.redis_url, decode_responses=True
        )
        self._index_ready = False
        self._index: SearchIndex | None = None

        # NOTE: embeddings are produced through the OpenAI SDK directly.
        # redisvl's OpenAITextVectorizer performs a live "dimension check" call
        # during construction, which would fail startup offline; we pin dims in
        # settings instead (1536 for text-embedding-3-small).
        self.llm: OpenAI | None = None
        if self.settings.openai_api_key:
            kwargs: dict[str, str] = {"api_key": self.settings.openai_api_key}
            if self.settings.openai_base_url:
                kwargs["base_url"] = self.settings.openai_base_url
            self.llm = OpenAI(**kwargs)

    # -- lifecycle ----------------------------------------------------------

    def ensure_ready(self) -> None:
        """Ping Redis and (once) create the vector index; raise if unavailable."""
        try:
            self.redis.ping()
        except Exception as exc:
            raise ConnectionError(
                f"Redis unreachable at {self.settings.redis_url}"
            ) from exc
        if not self._index_ready:
            self._ensure_index()

    def _ensure_index(self) -> None:
        schema = {
            "index": {
                "name": self.settings.redis_index_name,
                "prefix": self._vec_prefix(),
                "storage_type": "hash",
            },
            "fields": [
                {"name": "query", "type": "text"},
                {"name": "answer", "type": "text"},
                {"name": "namespace", "type": "tag"},
                {"name": "version", "type": "tag"},
                {"name": "tier", "type": "tag"},
                {"name": "user", "type": "tag"},
                {"name": "input_tokens", "type": "numeric"},
                {"name": "output_tokens", "type": "numeric"},
                {
                    "name": "embedding",
                    "type": "vector",
                    "attrs": {
                        "algorithm": "flat",
                        "dims": self.settings.embedding_dimensions,
                        "distance_metric": "cosine",
                        "datatype": "float32",
                    },
                },
            ],
        }
        self._index = SearchIndex.from_dict(schema, redis_client=self.redis)
        # overwrite=True is idempotent: recreates the schema when needed while
        # keeping existing documents (drop=False keeps the data intact).
        self._index.create(overwrite=True)
        self._index_ready = True
        logger.info("Vector index '%s' ready", self.settings.redis_index_name)

    def close(self) -> None:
        try:
            self.redis.close()
        except Exception:  # pragma: no cover - best-effort shutdown
            pass

    # -- key helpers ---------------------------------------------------------

    def _composite(self, ctx: RequestContext) -> str:
        return CacheKey.composite_hash(
            ctx.model, ctx.system_prompt_version, ctx.tools, ctx.customer_tier
        )

    def _namespace(self, ctx: RequestContext, composite: str) -> str:
        return CacheKey.namespace(ctx.user_id, composite)

    def _vec_prefix(self) -> str:
        return f"{self.settings.redis_key_prefix}:vec:"

    def _exact_key(self, ctx: RequestContext, namespace: str) -> str:
        qhash = hashlib.sha256(ctx.query.encode("utf-8")).hexdigest()
        return (
            f"{self.settings.redis_key_prefix}:exact:"
            f"{ctx.system_prompt_version}:{namespace}:{qhash}"
        )

    def _vec_key(self, ctx: RequestContext, namespace: str, doc_id: str) -> str:
        return (
            f"{self.settings.redis_key_prefix}:vec:"
            f"{ctx.system_prompt_version}:{namespace}:{doc_id}"
        )

    @staticmethod
    def _glob_escape(value: str) -> str:
        """Escape Redis MATCH glob metacharacters from untrusted input."""
        return re.sub(r"([*?\[\]])", r"\\\1", value)

    # -- pricing --------------------------------------------------------------

    def _llm_cost(self, input_tokens: int, output_tokens: int) -> float:
        p = self.settings
        return (
            input_tokens * p.input_token_price_per_1m
            + output_tokens * p.output_token_price_per_1m
        ) / 1_000_000

    def _embedding_cost(self, tokens: int) -> float:
        return tokens * self.settings.embedding_token_price_per_1m / 1_000_000

    # -- metrics ---------------------------------------------------------------

    def _record(self, mapping: MetricRecord) -> None:
        pipe = self.redis.pipeline(transaction=False)
        for field, value in mapping.items():
            if value > 0:
                if float(value).is_integer():
                    pipe.hincrby(METRICS_KEY, field, int(value))
                else:
                    pipe.hincrbyfloat(METRICS_KEY, field, float(value))
        pipe.execute()

    def _emit(
        self, events: list[LogEvent], level: str, message: str
    ) -> None:
        events.append(LogEvent(ts=time.time(), level=level, message=message))
        log_fn = logger.info if level == "success" else getattr(logger, "warning" if level == "warn" else level.lower())
        log_fn("[%s] %s", level.upper(), message)

    # -- layer 1: exact match ---------------------------------------------------

    def _exact_lookup(
        self, ctx: RequestContext, namespace: str
    ) -> dict[str, Any] | None:
        payload = self.redis.hgetall(self._exact_key(ctx, namespace))
        if not payload:
            return None
        return {
            "answer": payload.get("answer", ""),
            "query": payload.get("query", ctx.query),
            "input_tokens": int(payload.get("input_tokens", estimate_tokens(ctx.query))),
            "output_tokens": int(payload.get("output_tokens", 0)),
        }

    # -- layer 2: semantic match ------------------------------------------------

    @staticmethod
    def _field(result: Any, name: str, default: str = "") -> str:
        try:
            value = result[name]
        except (KeyError, IndexError, TypeError):
            return default
        return value if value else default

    def _semantic_lookup(
        self,
        ctx: RequestContext,
        namespace: str,
        embedding: list[float],
        threshold: float,
    ) -> tuple[dict[str, Any] | None, float | None]:
        if self._index is None:
            self.ensure_ready()

        filters = (
            (Tag("namespace") == namespace)
            & (Tag("version") == ctx.system_prompt_version)
            & (Tag("tier") == ctx.customer_tier)
        )
        query = VectorQuery(
            vector=embedding,
            vector_field_name="embedding",
            return_fields=[
                "query",
                "answer",
                "vector_distance",
                "user",
                "version",
                "input_tokens",
                "output_tokens",
            ],
            num_results=self.settings.vector_knn_results,
            filter_expression=filters,
        )
        try:
            results = self._index.query(query)
        except Exception as exc:  # unknown index / transient KNN failure
            logger.warning("Semantic lookup raised: %s", exc)
            return None, None

        if not results:
            return None, None

        top = results[0]
        cosine_distance = float(top["vector_distance"])
        similarity = max(0.0, 1.0 - cosine_distance)
        if similarity < threshold:
            return None, similarity

        return {
            "answer": self._field(top, "answer", ""),
            "query": self._field(top, "query", ctx.query),
            "user": self._field(top, "user", ctx.user_id),
            "input_tokens": int(float(self._field(top, "input_tokens", "0"))),
            "output_tokens": int(float(self._field(top, "output_tokens", "0"))),
            "key": top.id if hasattr(top, "id") else "",
        }, similarity

    # -- layer 3: provider call -------------------------------------------------

    def _provider_call(
        self,
        ctx: RequestContext,
        events: list[LogEvent],
        *,
        persist: bool,
        broadcast_query: str = "",
    ) -> PipelineResult:
        if self.llm is None:
            raise RuntimeError(
                "OpenAI API key missing. Set OPENAI_API_KEY or "
                "WARMSTART_OPENAI_API_KEY and restart the service."
            )
        started = time.perf_counter()
        completion = self.llm.chat.completions.create(
            model=ctx.model,
            messages=[
                {"role": "system", "content": ctx.system_prompt},
                {"role": "user", "content": ctx.query},
            ],
            user=ctx.user_id,
            temperature=0.2,
        )
        provider_ms = (time.perf_counter() - started) * 1000.0
        answer = completion.choices[0].message.content or ""
        usage = completion.usage
        input_tokens = usage.prompt_tokens if usage else estimate_tokens(ctx.query)
        output_tokens = usage.completion_tokens if usage else estimate_tokens(answer)
        cost = self._llm_cost(input_tokens, output_tokens)

        self._emit(
            events,
            "success",
            f"[PROVIDER] {ctx.model} {provider_ms:.0f}ms "
            f"{cost:.4f}$ ({input_tokens}+{output_tokens} tok) "
            f"{'→ cached' if persist else '(bypass)'}",
        )

        if persist:
            self._persist(ctx, answer, input_tokens, output_tokens)

        return PipelineResult(
            answer=answer,
            match_type="miss",
            latency_ms=provider_ms,
            cost_usd=cost,
            cost_saved_usd=0.0,
            similarity=None,
            tokens=TokenUsage(
                input=input_tokens, output=output_tokens, embedding=0
            ).as_dict(),
            cached=False,
        )

    def _persist(
        self,
        ctx: RequestContext,
        answer: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        composite = self._composite(ctx)
        namespace = self._namespace(ctx, composite)
        embedding = self._embed(ctx.query) if self.llm else []

        # Exact-match entry (raw text hash -> answer).
        exact_key = self._exact_key(ctx, namespace)
        self.redis.hset(
            exact_key,
            mapping={
                "query": ctx.query,
                "answer": answer,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": self._llm_cost(input_tokens, output_tokens),
                "namespace": namespace,
                "user": ctx.user_id,
                "tier": ctx.customer_tier,
                "version": ctx.system_prompt_version,
                "model": ctx.model,
            },
        )
        self.redis.expire(exact_key, self.settings.cache_ttl_seconds)

        # Semantic-match entry (query embedding + answer) in the vector index.
        doc = {
            "query": ctx.query,
            "answer": answer,
            "namespace": namespace,
            "user": ctx.user_id,
            "tier": ctx.customer_tier,
            "version": ctx.system_prompt_version,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "embedding": embedding,
        }
        vec_key = self._vec_key(
            ctx, namespace, CacheKey.document_id(ctx.query)
        )
        if self._index is not None and embedding:
            self._index.load(
                [doc], keys=[vec_key], ttl=self.settings.cache_ttl_seconds
            )

    def _embed(self, text: str) -> list[float]:
        """Embed text with text-embedding-3-small (dims must equal index dims)."""
        if self.llm is None:
            return []
        response = self.llm.embeddings.create(
            model=self.settings.embedding_model, input=text
        )
        return response.data[0].embedding

    # -- public entry points ----------------------------------------------------

    def raw_query(self, ctx: RequestContext) -> PipelineResult:
        """Bypass the cache entirely: straight to the provider."""
        events: list[LogEvent] = []
        started = time.perf_counter()
        result = self._provider_call(ctx, events, persist=False)
        result.match_type = "raw"
        result.latency_ms = (time.perf_counter() - started) * 1000.0
        result.events = [e.as_dict() for e in events]
        self._record(
            {
                "raw_requests": 1,
                "sum_raw_latency_ms": result.latency_ms,
                "raw_billed_cost_cents": result.cost_usd * 100.0,
            }
        )
        self._emit(events, "info", "[RAW] provider committed; cache bypassed")
        result.events = [e.as_dict() for e in events]
        return result

    def warmstart(self, ctx: RequestContext) -> PipelineResult:
        """Run the three-layer pipeline and return the winning path."""
        started = time.perf_counter()
        events: list[LogEvent] = []
        composite = self._composite(ctx)
        namespace = self._namespace(ctx, composite)

        self._emit(
            events,
            "info",
            f"[KEY] namespace={namespace} model={ctx.model} "
            f"version={ctx.system_prompt_version} tier={ctx.customer_tier} "
            f"tools={json.dumps(sorted(ctx.tools))}",
        )

        # ---- Layer 1: exact match --------------------------------------------
        t_layer = time.perf_counter()
        exact = self._exact_lookup(ctx, namespace)
        layer_ms = (time.perf_counter() - t_layer) * 1000.0
        self._emit(
            events,
            "success" if exact else "warn",
            f"[L1] EXACT {'HIT' if exact else 'MISS'} {layer_ms:.2f}ms",
        )
        if exact:
            hit_latency = (time.perf_counter() - started) * 1000.0
            finish = self._finish_hit(
                ctx, namespace, exact["answer"], "exact", None,
                exact["input_tokens"], exact["output_tokens"], hit_latency, events,
            )
            self._record(
                {
                    "requests": 1,
                    "hits": 1,
                    "exact_hits": 1,
                    "sum_warmstart_latency_ms": finish.latency_ms,
                }
            )
            return finish

        # ---- Layer 2: semantic match -----------------------------------------
        t_layer = time.perf_counter()
        embedding = self._embed(ctx.query)
        if not embedding:
            raise RuntimeError(
                "OpenAI API key missing. Set OPENAI_API_KEY or "
                "WARMSTART_OPENAI_API_KEY and restart the service."
            )
        embed_ms = (time.perf_counter() - t_layer) * 1000.0
        embed_tokens = estimate_tokens(ctx.query)
        self._emit(
            events,
            "info",
            f"[L2] EMBED text-embedding-3-small {embed_ms:.1f}ms dim={len(embedding)} "
            f"(infra {self._embedding_cost(embed_tokens):.5f}$)",
        )

        t_layer = time.perf_counter()
        semantic, similarity = self._semantic_lookup(
            ctx, namespace, embedding, self.settings.semantic_similarity_threshold
        )
        vec_ms = (time.perf_counter() - t_layer) * 1000.0
        if semantic is not None and similarity is not None:
            similarity = round(similarity, 4)
            self._emit(
                events,
                "success",
                f"[L2] VECTOR KNN {vec_ms:.1f}ms top sim={similarity} "
                f">= {self.settings.semantic_similarity_threshold} → HIT",
            )
            hit_latency = (time.perf_counter() - started) * 1000.0
            finish = self._finish_hit(
                ctx, namespace, semantic["answer"], "semantic", similarity,
                semantic["input_tokens"], semantic["output_tokens"], hit_latency, events,
            )
            finish.cached_doc = CachedDocument(
                answer=semantic["answer"],
                stored_query=semantic["query"],
                namespace=namespace,
                input_tokens=semantic["input_tokens"],
                output_tokens=semantic["output_tokens"],
                similarity=similarity,
                redis_key=semantic.get("key", ""),
            )
            self._record(
                {
                    "requests": 1,
                    "hits": 1,
                    "semantic_hits": 1,
                    "sum_warmstart_latency_ms": finish.latency_ms,
                }
            )
            return finish

        if similarity is not None:
            self._emit(
                events,
                "warn",
                f"[L2] VECTOR KNN {vec_ms:.1f}ms best sim={similarity:.4f} "
                f"< {self.settings.semantic_similarity_threshold} → MISS",
            )
        else:
            self._emit(
                events,
                "warn",
                f"[L2] VECTOR KNN {vec_ms:.1f}ms no candidates in namespace → MISS",
            )

        # ---- Layer 3: cache miss / provider call -----------------------------
        self._emit(
            events,
            "warn",
            f"[L3] CACHE MISS → calling {ctx.model}; "
            f"ttl={self.settings.cache_ttl_seconds}s",
        )
        result = self._provider_call(ctx, events, persist=True)
        result.latency_ms = (time.perf_counter() - started) * 1000.0
        result.events = [e.as_dict() for e in events]
        self._record(
            {
                "requests": 1,
                "misses": 1,
                "sum_warmstart_latency_ms": result.latency_ms,
            }
        )
        return result

    # -- shared helpers -----------------------------------------------------------

    def _finish_hit(
        self,
        ctx: RequestContext,
        namespace: str,
        answer: str,
        match_type: str,
        similarity: float | None,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
        events: list[LogEvent],
    ) -> PipelineResult:
        saved = self._llm_cost(input_tokens, output_tokens)
        self._record({"sum_cost_saved_cents": saved * 100.0})
        self._append_audit(
            {
                "ts": time.time(),
                "user": ctx.user_id,
                "namespace": namespace,
                "query": ctx.query,
                "match": match_type,
                "similarity": similarity,
                "saved_usd": round(saved, 6),
            }
        )
        self._emit(
            events,
            "info",
            f"[OK] {match_type.upper()} hit → cost=$0.0000 saved≈{saved:.4f}$",
        )
        return PipelineResult(
            answer=answer,
            match_type=match_type,
            latency_ms=latency_ms,
            cost_usd=0.0,
            cost_saved_usd=saved,
            similarity=similarity,
            tokens=TokenUsage(
                input=input_tokens, output=output_tokens, embedding=estimate_tokens(ctx.query)
            ).as_dict(),
            cached=True,
            events=[e.as_dict() for e in events],
        )

    def _append_audit(self, entry: dict[str, Any]) -> None:
        key = f"{self.settings.redis_key_prefix}:audit"
        self.redis.lpush(key, json.dumps(entry, default=str))
        self.redis.ltrim(key, 0, 199)

    # -- admin -------------------------------------------------------------------

    def bust_cache(self, system_prompt_version: str) -> tuple[int, list[str]]:
        """Delete every cached entry tagged with the given prompt version."""
        escaped = self._glob_escape(system_prompt_version)
        patterns = (
            f"{self.settings.redis_key_prefix}:exact:{escaped}:*",
            f"{self.settings.redis_key_prefix}:vec:{escaped}:*",
        )
        keys: list[str] = []
        for pattern in patterns:
            for key in self.redis.scan_iter(match=pattern, count=500):
                if isinstance(key, str):
                    keys.append(key)
        if keys:
            self.redis.unlink(*keys)
        # Cost billing for already-served hits remains, but the "saved so far"
        # counter is reset so the dashboard reflects the new prompt era.
        self.redis.hdel(METRICS_KEY, "sum_cost_saved_cents")
        logger.warning(
            "Cache busted for prompt version %s: %d keys removed",
            system_prompt_version,
            len(keys),
        )
        return len(keys), keys