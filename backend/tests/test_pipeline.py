"""Offline pipeline tests — fakeredis + stubbed OpenAI/vectorizer.

Exercises exact-hit, semantic-hit, semantic-miss->provider, metrics and bust.

Usage (from the `backend/` directory):

    python tests/test_pipeline.py            # plain script
    python -m pytest tests/test_pipeline.py  # pytest runner

Requires the dev deps from requirements-dev.txt (fakeredis, pytest).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fakeredis

from app.cache_engine import (
    CacheKey,
    METRICS_KEY,
    RequestContext,
    WarmstartCacheEngine,
)
from app.config import Settings

from tests import _fakes as fakes

OPENAI_KEY = "sk-test-dummy"


def make_engine(redis, hits=None):
    engine = WarmstartCacheEngine(
        redis=redis, settings=Settings(openai_api_key=OPENAI_KEY)
    )
    engine._index_ready = True
    engine._index = (
        fakes.FakeIndex(redis, hits) if hits is not None else fakes.FakeIndex(redis)
    )
    engine.llm = fakes.FakeLLM()
    return engine


def ctx(query="Where is my order?", user="alice", tier="Free", version="v1.0", tools=None):
    return RequestContext(
        query=query,
        user_id=user,
        customer_tier=tier,
        system_prompt_version=version,
        tools=tools or [],
        model="gpt-4o-mini",
    )


def test_keys():
    c1 = CacheKey.composite_hash("gpt-4o-mini", "v1.0", [], "Free")
    c2 = CacheKey.composite_hash("gpt-4o-mini", "v1.0", [], "Free")
    c3 = CacheKey.composite_hash("gpt-4o-mini", "v1.0", ["search"], "Free")
    assert c1 == c2 and len(c1) == 32, "composite deterministic & md5 length"
    assert c1 != c3, "tools change the composite"
    ns_a = CacheKey.namespace("alice", c1)
    ns_b = CacheKey.namespace("bob", c1)
    assert ns_a != ns_b, "tenant isolation"


def test_exact_hit_then_miss():
    redis = fakeredis.FakeRedis(decode_responses=True)
    engine = make_engine(redis)
    r1 = engine.warmstart(ctx())  # miss -> provider -> persisted
    assert r1.match_type == "miss", r1.match_type
    assert r1.cost_usd > 0
    assert r1.answer  # persisted answer

    r2 = engine.warmstart(ctx())  # now exact hit
    assert r2.match_type == "exact", r2.match_type
    assert r2.cached is True
    assert r2.cost_usd == 0.0
    assert r2.cost_saved_usd > 0
    assert r2.latency_ms < 1000

    m = redis.hgetall(METRICS_KEY)
    assert int(m["requests"]) == 2
    assert int(m["hits"]) == 1
    assert int(m["misses"]) == 1
    assert int(m["exact_hits"]) == 1


def test_semantic_hit():
    redis = fakeredis.FakeRedis(decode_responses=True)
    c = CacheKey.composite_hash("gpt-4o-mini", "v1.0", [], "Free")
    ns = CacheKey.namespace("alice", c)
    hit = {
        "query": "where is my order",
        "answer": "cached order answer",
        "vector_distance": "0.05",
        "user": "alice",
        "version": "v1.0",
        "input_tokens": "10",
        "output_tokens": "30",
        "_key": f"warmstart:vec:v1.0:{ns}:doc",
    }
    engine = make_engine(redis, hits=[hit])
    r = engine.warmstart(ctx(query="track my package"))
    assert r.match_type == "semantic", r.match_type
    assert r.cached is True
    assert r.similarity == round(0.95, 4), r.similarity
    assert r.cached_doc is not None
    assert r.cached_doc.stored_query == "where is my order"

    m = redis.hgetall(METRICS_KEY)
    assert int(m["semantic_hits"]) == 1
    assert float(m["sum_cost_saved_cents"]) > 0


def test_semantic_below_threshold_misses():
    redis = fakeredis.FakeRedis(decode_responses=True)
    c = CacheKey.composite_hash("gpt-4o-mini", "v1.0", [], "Free")
    ns = CacheKey.namespace("alice", c)
    hit = {
        "query": "unrelated",
        "answer": "cached",
        "vector_distance": "0.5",
        "user": "alice",
        "version": "v1.0",
        "input_tokens": "1",
        "output_tokens": "1",
        "_key": f"warmstart:vec:v1.0:{ns}:doc",
    }
    engine = make_engine(redis, hits=[hit])
    r = engine.warmstart(ctx(query="something else entirely"))
    assert r.match_type == "miss", r.match_type  # provider fallback
    assert r.cost_usd > 0


def test_client_isolation():
    redis = fakeredis.FakeRedis(decode_responses=True)
    engine = make_engine(redis)
    engine.warmstart(ctx(query="order status", user="alice"))
    # bob's namespace must NOT see alice's exact entry
    r = engine.warmstart(ctx(query="order status", user="bob"))
    assert r.match_type == "miss", "cross-user leak!"
    assert r.cached is False


def test_bust_cache_by_version():
    redis = fakeredis.FakeRedis(decode_responses=True)
    engine = make_engine(redis)
    engine.warmstart(ctx(query="hello world", version="v1.0", user="u1"))
    engine.warmstart(ctx(query="other question", version="v1.0", user="u1"))
    n, keys = engine.bust_cache("v1.0")
    assert n == 4, (n, keys)  # 2 exact + 2 vec
    assert engine.redis.dbsize() == 1, "only metrics hash left"
    r = engine.warmstart(ctx(query="hello world", version="v1.0", user="u1"))
    assert r.match_type == "miss", "bust failed"


def test_raw_bypass_does_not_cache():
    redis = fakeredis.FakeRedis(decode_responses=True)
    engine = make_engine(redis)
    r = engine.raw_query(ctx(query="hello"))
    assert r.match_type == "raw"
    cache_keys = [
        k
        for k in redis.scan_iter(match="warmstart:*")
        if k.startswith(("warmstart:exact:", "warmstart:vec:"))
    ]
    assert cache_keys == [], cache_keys
    m = redis.hgetall(METRICS_KEY)
    assert int(m["raw_requests"]) == 1
    assert float(m["sum_raw_latency_ms"]) > 0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print("ALL OFFLINE TESTS PASSED")