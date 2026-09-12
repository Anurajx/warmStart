"""Shared stubs for offline tests: fake LLM client + redisvl index stub."""

import types


class FakeUsage:
    prompt_tokens = 12
    completion_tokens = 40


class FakeChoice:
    def __init__(self, content):
        self.message = types.SimpleNamespace(content=content)


class FakeCompletion:
    choices = [FakeChoice("Your order is on its way (from fake provider).")]
    usage = FakeUsage()


class FakeLLM:
    """Stand-in for openai.OpenAI — deterministic embedding + completion."""

    def __init__(self):
        self.embeddings = types.SimpleNamespace(
            create=lambda **kwargs: types.SimpleNamespace(
                data=[types.SimpleNamespace(index=0, embedding=[0.1] * 3)]
            )
        )
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self.create)
        )

    def create(self, **kwargs):
        return FakeCompletion()


class FakeIndex:
    """Stub of redisvl SearchIndex that persists documents to fake Redis."""

    def __init__(self, redis, hits: list[dict] | None = None):
        self.redis = redis
        self.hits = hits or []

    def query(self, query):  # noqa: A003 (duck-typed)
        if not self.hits:
            return []

        class _R(dict):  # mimics redisvl Result: dict-like + .id
            pass

        out = []
        for h in self.hits:
            r = _R(h)
            r.id = h.get("_key", "warmstart:vec:v1.0:ns:doc")
            out.append(r)
        return out

    def load(self, data, keys=None, ttl=None, **kwargs):
        for doc, key in zip(data, keys or []):
            mapping = {k: v for k, v in doc.items() if k != "embedding"}
            mapping["embedding"] = str(doc.get("embedding", ""))
            self.redis.hset(key, mapping=mapping)
            if ttl:
                self.redis.expire(key, ttl)
        return list(keys or [])