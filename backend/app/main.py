"""FastAPI application for Warmstart.

Endpoints
---------
POST /api/query/raw         - Bypass the cache; measure real provider latency/cost.
POST /api/query/warmstart   - Run the three-layer Warmstart pipeline.
POST /api/admin/bust-cache  - Invalidate every cached entry for a prompt version.
GET  /api/metrics           - Aggregated hit rate, savings, latency reduction,
                              false-hit evaluations.
GET  /api/health            - Liveness + Redis readiness probe.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .cache_engine import (
    METRICS_KEY,
    RequestContext,
    WarmstartCacheEngine,
)
from .config import Settings, get_settings
from .evaluator import HitEvaluator

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("warmstart.api")

settings = get_settings()
engine = WarmstartCacheEngine()
evaluator = HitEvaluator(engine.redis, settings)


# -- request / response models ---------------------------------------------------

class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000, description="User prompt")
    user_id: str = Field(default="guest", min_length=1, max_length=64)
    customer_tier: Literal["Free", "Gold"] = Field(
        default="Free", description="Customer tier drives tier-scoped prompts/key space"
    )
    system_prompt_version: str = Field(
        default="v1.0",
        pattern=r"^[\w.\-]+$",
        description="Deployed system-prompt version tag (cache partition key)",
    )
    tools: list[str] = Field(default_factory=list, description="Available tool names")
    model: str = Field(default=settings.llm_model, description="Provider model")


class QueryResponse(BaseModel):
    query: str
    answer: str
    match_type: Literal["exact", "semantic", "miss", "raw"]
    similarity: float | None
    latency_ms: float
    cost_usd: float
    cost_saved_usd: float
    tokens: dict[str, int]
    cached: bool
    events: list[dict[str, Any]]


class BustCacheRequest(BaseModel):
    system_prompt_version: str = Field(pattern=r"^[\w.\-]+$")


class BustCacheResponse(BaseModel):
    system_prompt_version: str
    keys_deleted: int
    deleted: list[str]


class MetricsResponse(BaseModel):
    requests: int
    hits: int
    misses: int
    exact_hits: int
    semantic_hits: int
    hit_rate_pct: float
    total_money_saved_usd: float
    raw_avg_latency_ms: float
    warmstart_avg_latency_ms: float
    latency_reduction_pct: float
    evaluations: int
    false_hits: int
    false_hit_rate_pct: float
    cache_entries: int


# -- startup / shutdown -------------------------------------------------------------

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Warm the vector index. If Redis is down at boot we simply log and let
    # each request surface a clear 503 once it is reachable again.
    try:
        await asyncio.to_thread(engine.ensure_ready)
    except Exception:
        logger.exception("Redis unavailable at startup; requests will 503 until ready")
    yield
    engine.close()


app = FastAPI(
    title="Warmstart — AI Cost & Latency Firewall",
    version=settings.version,
    description=(
        "Redirects LLM traffic through a Redis-backed three-layer cache: "
        "exact match, semantic match, provider fallback."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        os.getenv("FRONTEND_ORIGIN", ""),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_ready() -> None:
    try:
        engine.ensure_ready()
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _ctx(model: QueryRequest) -> RequestContext:
    return RequestContext(
        query=model.query,
        user_id=model.user_id,
        customer_tier=model.customer_tier,
        system_prompt_version=model.system_prompt_version,
        tools=model.tools,
        model=model.model,
    )


def _to_response(ctx: QueryRequest, result: Any) -> QueryResponse:
    return QueryResponse(
        query=ctx.query,
        answer=result.answer,
        match_type=result.match_type,
        similarity=result.similarity,
        latency_ms=round(result.latency_ms, 2),
        cost_usd=round(result.cost_usd, 6),
        cost_saved_usd=round(result.cost_saved_usd, 6),
        tokens=result.tokens,
        cached=result.cached,
        events=result.events,
    )


# -- routes ---------------------------------------------------------------------------

@app.get("/api/health", tags=["ops"])
def health() -> dict[str, Any]:
    try:
        engine.redis.ping()
        redis_ok = True
    except Exception:
        redis_ok = False
    return {
        "status": "ok" if redis_ok else "degraded",
        "redis": redis_ok,
        "llm": engine.llm is not None,
        "version": settings.version,
    }


@app.post("/api/query/raw", tags=["query"])
def query_raw(model: QueryRequest) -> QueryResponse:
    """Direct provider call; no cache participation. Measures real latency/cost."""
    _require_ready()
    try:
        result = engine.raw_query(_ctx(model))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _to_response(model, result)


@app.post("/api/query/warmstart", tags=["query"])
async def query_warmstart(model: QueryRequest) -> QueryResponse:
    """Run the three-layer pipeline: exact → semantic → provider."""
    _require_ready()
    try:
        result = await asyncio.to_thread(engine.warmstart, _ctx(model))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Kick off the LLM judge for semantic hits without blocking the response.
    if result.match_type == "semantic" and result.cached_doc is not None:
        asyncio.create_task(
            evaluator.evaluate(result.cached_doc, model.query)
        )
    return _to_response(model, result)


@app.post("/api/admin/bust-cache", tags=["admin"])
def bust_cache(model: BustCacheRequest) -> BustCacheResponse:
    """Invalidate all cached entries tagged with a prompt version (policy deploy)."""
    _require_ready()
    deleted_count, deleted = engine.bust_cache(model.system_prompt_version)
    logger.warning(
        "ADMIN: cache invalidated for prompt version %s (%d keys)",
        model.system_prompt_version,
        deleted_count,
    )
    return BustCacheResponse(
        system_prompt_version=model.system_prompt_version,
        keys_deleted=deleted_count,
        deleted=deleted,
    )


@app.get("/api/metrics", tags=["ops"])
def metrics() -> MetricsResponse:
    """Aggregated hit rate, money saved, latency reduction and false-hit rate."""
    _require_ready()
    data: dict[str, str] = engine.redis.hgetall(METRICS_KEY)
    i = lambda f: int(float(data.get(f, 0)))  # noqa: E731
    f = lambda f: float(data.get(f, 0.0))  # noqa: E731

    requests = i("requests")
    hits = i("hits")
    raw_requests = i("raw_requests")
    evaluations = i("evaluations")
    false_hits = i("false_hits")

    warm_avg = (
        f("sum_warmstart_latency_ms") / requests if requests else 0.0
    )
    raw_avg = (
        f("sum_raw_latency_ms") / raw_requests if raw_requests else 0.0
    )
    latency_reduction = (
        (1.0 - warm_avg / raw_avg) * 100.0
        if raw_avg > 0 and warm_avg > 0
        else 0.0
    )

    return MetricsResponse(
        requests=requests,
        hits=hits,
        misses=i("misses"),
        exact_hits=i("exact_hits"),
        semantic_hits=i("semantic_hits"),
        hit_rate_pct=round(hits / requests * 100.0, 2) if requests else 0.0,
        total_money_saved_usd=round(f("sum_cost_saved_cents") / 100.0, 4),
        raw_avg_latency_ms=round(raw_avg, 2),
        warmstart_avg_latency_ms=round(warm_avg, 2),
        latency_reduction_pct=round(max(0.0, latency_reduction), 2),
        evaluations=evaluations,
        false_hits=false_hits,
        false_hit_rate_pct=round(false_hits / evaluations * 100.0, 2) if evaluations else 0.0,
        cache_entries=engine.redis.dbsize(),
    )